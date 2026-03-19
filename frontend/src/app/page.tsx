import { redirect } from "next/navigation";

// "/" → dashboard page is handled by (dashboard)/page.tsx.
// This file exists to redirect any direct "/" hit to the dashboard home.
// Since (dashboard)/page.tsx also resolves to "/" in the route group,
// Next.js picks this file — so we redirect to the query page after login.
export default function RootPage() {
    redirect("/query");
}
