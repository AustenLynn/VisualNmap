import type { StatusInfo } from "../api/types";

export function StatusBanner({ status }: { status: StatusInfo }) {
  const banners = [];
  if (!status.nmap_found) {
    banners.push(
      <div key="nmap" className="banner banner-error" role="alert">
        <strong>Nmap is not installed.</strong> Install it with <code>sudo apt install nmap</code>, then restart VisualNmap.
      </div>,
    );
  }
  if (!status.can_raw) {
    banners.push(
      <div key="root" className="banner banner-warn">
        <strong>Started without sudo:</strong> options marked 🔒 are disabled because they need raw network access.
        Restart with <code>./run.sh</code> (it uses sudo) to unlock them.
      </div>,
    );
  }
  if (status.in_container) {
    banners.push(
      <div key="docker" className="banner banner-info">
        <strong>Running in Docker:</strong> LAN device discovery is limited, and <code>localhost</code> means the
        container. Scan your PC by its LAN IP instead.
      </div>,
    );
  }
  if (banners.length === 0) return null;
  return <div className="banners">{banners}</div>;
}
