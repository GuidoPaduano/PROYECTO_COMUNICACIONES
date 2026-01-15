// Pequeña utilidad para invalidar/avisar que cambió el estado de la bandeja (no leídos)

export const INBOX_EVENT = "inbox-changed";

/** Dispara un evento global (window) para notificar que cambió la bandeja. */
export function notifyInboxChanged() {
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(INBOX_EVENT));
    }
  } catch {}
}
