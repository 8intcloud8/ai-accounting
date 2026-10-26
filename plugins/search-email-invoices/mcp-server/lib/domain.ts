/** Extracts and lowercases the domain from an email address. */
export function domainOf(email: string): string {
  const at = email.lastIndexOf("@");
  return at === -1 ? email.toLowerCase() : email.slice(at + 1).toLowerCase();
}
