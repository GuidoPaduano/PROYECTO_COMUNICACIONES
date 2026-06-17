// Pequeña utilidad para invalidar/avisar que cambió el estado de la bandeja (no leídos)

export const INBOX_EVENT = "inbox-changed";
export const INBOX_STORAGE_KEY = "inbox-changed-at";

/** Dispara un evento global (window) para notificar que cambió la bandeja. */
export function notifyInboxChanged() {
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(INBOX_EVENT));
      window.localStorage?.setItem(INBOX_STORAGE_KEY, String(Date.now()));
    }
  } catch {}
}
