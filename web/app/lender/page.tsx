import { redirect } from "next/navigation";

/**
 * The old light "lender" dashboard has been replaced by the dedicated dark
 * auditor console at /auditor. Keep this route as a permanent redirect so any
 * saved links or bookmarks keep working.
 */
export default function LenderPage() {
  redirect("/auditor");
}
