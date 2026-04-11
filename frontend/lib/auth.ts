const TOKEN_KEY = "pragent_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return (
    getCookie(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || null
  );
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

export interface TokenUser {
  id: number;
  username: string;
}

export function getCurrentUser(): TokenUser | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return {
      id: Number(payload.sub),
      username: payload.username ?? "",
    };
  } catch {
    return null;
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}
