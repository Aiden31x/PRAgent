import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");

  if (!code) {
    return NextResponse.redirect(new URL("/?error=no_code", request.url));
  }

  try {
    const res = await fetch(`${API_BASE}/auth/github/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    if (!res.ok) {
      return NextResponse.redirect(new URL("/?error=auth_failed", request.url));
    }

    const data = await res.json();
    const token: string = data.token;

    const response = NextResponse.redirect(new URL("/", request.url));
    response.cookies.set("pragent_token", token, {
      path: "/",
      maxAge: 60 * 60 * 24 * 7,
      sameSite: "lax",
      httpOnly: false,
    });

    return response;
  } catch {
    return NextResponse.redirect(new URL("/?error=auth_error", request.url));
  }
}
