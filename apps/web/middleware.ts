import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Authenticated areas. Public surfaces (hub, pricing, reader, public profiles,
// and the Clerk /login + /signup pages themselves) stay open.
const isProtected = createRouteMatcher([
  "/studio(.*)",
  "/inbox(.*)",
  "/settings(.*)",
  "/publish(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Run on everything except Next internals and static files, plus always on API routes.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpg|jpeg|gif|png|svg|ico|webp|woff2?|ttf|map)).*)",
    "/(api|trpc)(.*)",
  ],
};
