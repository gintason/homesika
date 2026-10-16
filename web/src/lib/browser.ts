/** Thin wrapper over full-page navigation so tests can observe redirects to the payment gateway. */
export const browser = {
  assign(url: string): void {
    window.location.assign(url);
  },
};
