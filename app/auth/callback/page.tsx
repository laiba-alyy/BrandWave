"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";

export default function CallbackPage() {
  const router = useRouter();
  const supabase = createClient();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleCallback = async () => {
      try {
        const url = new URL(window.location.href);
        const code = url.searchParams.get("code");
        const mode = url.searchParams.get("mode");
        const callbackError = url.searchParams.get("error");
        const callbackErrorDescription = url.searchParams.get("error_description");

        if (callbackError) {
          const readableError =
            callbackErrorDescription?.replace(/\+/g, " ") || "Authentication callback failed";
          throw new Error(readableError);
        }

        // Backward compatibility for links already sent with callback mode.
        if (mode === "email-verification") {
          router.replace(`/auth/verify-email?${url.searchParams.toString()}`);
          return;
        }

        if (code) {
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
          if (exchangeError) {
            const msg = exchangeError.message.toLowerCase();
            // With implicit flow and some email clients, PKCE verifier may be unavailable.
            // In that case we continue and rely on getSession()/URL-detected session.
            if (!msg.includes("pkce code verifier not found")) {
              throw exchangeError;
            }
          }
        }

        // OAuth callback for admin/business signup or login.
        const {
          data: { session },
          error: sessionError,
        } = await supabase.auth.getSession();
        if (sessionError) throw sessionError;
        if (!session?.user?.email) throw new Error("No authenticated user");

        const businessName = sessionStorage.getItem("businessName") || "My Business";

        const { data: existingUser, error: fetchError } = await supabase
          .from("users")
          .select("id, role")
          .eq("id", session.user.id)
          .maybeSingle();
        if (fetchError) throw fetchError;

        // Role AB sessionStorage se NAHI aata.
        //
        // Pehle yahan `selectedRole` parha jata tha, jo /admin-login ka Google
        // button set karta hai — aur sessionStorage puri tarah client ki cheez
        // hai. Yani koi bhi banda /admin-login khol kar, kisi bhi Google account
        // se sign in kar ke, apni row `role: 'admin'` ke saath insert kar leta
        // tha. Koi exploit nahi chahiye tha, wo ek supported UI path tha.
        //
        // Ab role sirf DB se parha jata hai: nayi row table ke default ('user')
        // par banti hai, aur promote karna sirf service-role key se mumkin hai.
        let appRole = existingUser?.role;

        if (!existingUser) {
          const { data: insertedUser, error: insertError } = await supabase
            .from("users")
            .insert({
              id: session.user.id,
              email: session.user.email,
              business_name: businessName,
              auth_provider: "google",
            })
            .select("role")
            .single();
          if (insertError) throw insertError;
          appRole = insertedUser.role;
        }

        sessionStorage.removeItem("businessName");
        sessionStorage.removeItem("selectedRole");
        router.push(appRole === "admin" ? "/admin" : "/business");
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Authentication failed");
        setTimeout(() => router.push("/login"), 2500);
      } finally {
        setLoading(false);
      }
    };

    handleCallback();
  }, [router, supabase]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-secondary-50">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600 font-semibold">Authenticating...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-secondary-50">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md text-center">
          <div className="text-red-600 text-5xl mb-4">❌</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Authentication Failed</h2>
          <p className="text-gray-600 text-sm mb-6">{error}</p>
          <button
            onClick={() => router.push("/login")}
            className="w-full px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 font-semibold"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return null;
}
