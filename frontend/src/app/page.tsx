// app/page.tsx — Redirect to workspace
import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/workspace");
}
