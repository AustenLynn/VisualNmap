import { Link } from "react-router-dom";

export function Home() {
  return (
    <div className="home">
      <div className="mode-cards">
        <Link to="/guided" className="mode-card">
          <span className="mode-icon" aria-hidden>🧭</span>
          <span className="mode-title">Guide me</span>
          <span className="mode-text">Answer four simple questions and VisualNmap builds the right scan, explaining every step.</span>
        </Link>
        <Link to="/builder" className="mode-card">
          <span className="mode-icon" aria-hidden>⚡</span>
          <span className="mode-title">I know what I want</span>
          <span className="mode-text">Every supported option on one screen, grouped by purpose, with the exact command always visible.</span>
        </Link>
      </div>
      <section className="card">
        <h2>What is Nmap?</h2>
        <p>
          Nmap ("Network Mapper") is a free tool that sends carefully crafted packets to computers and reads the replies.
          From those replies it works out which devices are online, which ports (doors into a computer) are open, what
          software is listening behind them, and often which operating system a device runs.
        </p>
        <p>
          Network admins use it to keep an inventory and spot things that shouldn't be exposed; security testers use it as
          the first step of an assessment. VisualNmap shows you the exact nmap command it runs, so you learn the real tool
          as you go.
        </p>
      </section>
      <p className="legal">
        ⚠️ Only scan computers and networks you own or have written permission to test. Good practice targets: your own
        router, your own PCs, lab VMs, and <code>scanme.nmap.org</code>.
      </p>
    </div>
  );
}
