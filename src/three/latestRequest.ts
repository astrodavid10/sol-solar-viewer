// =====================================================================
// "Latest request wins" for async loads that paint shared state
// =====================================================================
// Each begin() supersedes every earlier ticket. A completion checks
// isCurrent() before it paints, so a slow load that lands after the guest
// has moved on (a channel switch, a scrub) can never overwrite the newer
// choice. Before this (T34): picking Magnetic Map while the default 4K map
// was still downloading painted Coronal Loops over it when that download
// finished, under a panel that said Magnetic Map.
//
// No three.js or WWT imports (footgun 12), so it is unit-testable as is.

export interface Ticket {
  readonly key: string;
  readonly seq: number;
}

export class LatestRequest {
  private seq = 0;
  private current: Ticket | null = null;

  /** Start a request for `key`, superseding any earlier one. */
  begin(key: string): Ticket {
    this.seq += 1;
    this.current = { key, seq: this.seq };
    return this.current;
  }

  /** True while `ticket` is the most recent request. */
  isCurrent(ticket: Ticket): boolean {
    return this.current !== null && this.current.seq === ticket.seq;
  }

  /** The key of the request in flight, or null. */
  inFlight(): string | null {
    return this.current ? this.current.key : null;
  }

  /** Forget the current request (it finished, failed, or was abandoned). */
  clear(ticket?: Ticket): void {
    if (!ticket || this.isCurrent(ticket)) { this.current = null; }
  }
}
