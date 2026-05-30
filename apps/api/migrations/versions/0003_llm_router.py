"""LLM router: replace mode + llm_profiles with a 3-lane JSON column

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30

Migrates existing per-user LLM config into a single `lanes` JSON:
  - seed creative/technical/embedding from the flat default columns
  - override each lane from any matching llm_profiles row (role = creative|technical|embedding)
  - task:<page> profiles are dropped (the old "custom" mode is removed)
Then drops the llm_profiles table and the mode + flat provider columns.
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add the lanes column (nullable for the backfill step).
    with op.batch_alter_table("user_llm_settings") as batch:
        batch.add_column(sa.Column("lanes", sa.JSON, nullable=True))

    # 2. Backfill lanes from existing flat columns + llm_profiles.
    settings_rows = conn.execute(sa.text(
        "SELECT user_id, provider, base_url, model, embed_model, api_key_ciphertext FROM user_llm_settings"
    )).fetchall()

    # Collect role profiles per user (creative|technical|embedding only).
    profiles: dict[str, dict[str, dict]] = {}
    try:
        prof_rows = conn.execute(sa.text(
            "SELECT user_id, role, provider, base_url, model, embed_model, api_key_ciphertext FROM llm_profiles"
        )).fetchall()
        for r in prof_rows:
            role = r[1]
            if role in ("creative", "technical", "embedding"):
                profiles.setdefault(r[0], {})[role] = {
                    "provider": r[2], "base_url": r[3] or "", "model": r[4] or "",
                    "embed_model": r[5] or "", "api_key_ciphertext": r[6] or "",
                }
    except Exception:
        pass  # llm_profiles may not exist in some states; default-seed only

    for row in settings_rows:
        uid = row[0]
        default = {
            "provider": row[1] or "lmstudio", "base_url": row[2] or "", "model": row[3] or "",
            "embed_model": row[4] or "", "api_key_ciphertext": row[5] or "",
        }
        user_profiles = profiles.get(uid, {})
        lanes = {
            "creative": user_profiles.get("creative", dict(default)),
            "technical": user_profiles.get("technical", dict(default)),
            "embedding": user_profiles.get("embedding", dict(default)),
        }
        stmt = sa.text(
            "UPDATE user_llm_settings SET lanes = :lanes WHERE user_id = :uid"
        ).bindparams(sa.bindparam("lanes", type_=sa.JSON))
        conn.execute(stmt, {"lanes": lanes, "uid": uid})

    # 3. Drop llm_profiles + the now-unused flat columns.
    op.drop_table("llm_profiles")
    with op.batch_alter_table("user_llm_settings") as batch:
        for col in ("mode", "provider", "base_url", "model", "embed_model", "api_key_ciphertext"):
            batch.drop_column(col)


def downgrade() -> None:
    # Recreate the flat columns + llm_profiles (lossy: lane divergence is not restored).
    with op.batch_alter_table("user_llm_settings") as batch:
        batch.add_column(sa.Column("mode", sa.String(16), nullable=False, server_default="single"))
        batch.add_column(sa.Column("provider", sa.String(32), nullable=False, server_default="lmstudio"))
        batch.add_column(sa.Column("base_url", sa.String(500), nullable=False, server_default=""))
        batch.add_column(sa.Column("model", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("embed_model", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("api_key_ciphertext", sa.Text, nullable=False, server_default=""))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT user_id, lanes FROM user_llm_settings")).fetchall()
    for uid, lanes_json in rows:
        try:
            creative = (json.loads(lanes_json) if isinstance(lanes_json, str) else (lanes_json or {})).get("creative", {})
        except Exception:
            creative = {}
        conn.execute(sa.text(
            "UPDATE user_llm_settings SET provider=:p, base_url=:b, model=:m, embed_model=:e, api_key_ciphertext=:k WHERE user_id=:uid"
        ), {
            "p": creative.get("provider", "lmstudio"), "b": creative.get("base_url", ""),
            "m": creative.get("model", ""), "e": creative.get("embed_model", ""),
            "k": creative.get("api_key_ciphertext", ""), "uid": uid,
        })

    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="lmstudio"),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("model", sa.String(200), nullable=False, server_default=""),
        sa.Column("embed_model", sa.String(200), nullable=False, server_default=""),
        sa.Column("api_key_ciphertext", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role", name="uq_llm_profile_user_role"),
    )
    op.create_index("ix_llm_profiles_user_id", "llm_profiles", ["user_id"])

    with op.batch_alter_table("user_llm_settings") as batch:
        batch.drop_column("lanes")
