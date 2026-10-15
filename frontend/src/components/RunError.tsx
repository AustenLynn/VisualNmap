import { Link } from "react-router-dom";
import type { ApiError } from "../api/client";

export function RunError({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <div className="banner banner-error" role="alert">
      {error.message}
      {error.body.active_scan_id && (
        <>
          {" "}
          <Link to={`/scans/${error.body.active_scan_id}`}>Open the running scan</Link>
        </>
      )}
    </div>
  );
}
