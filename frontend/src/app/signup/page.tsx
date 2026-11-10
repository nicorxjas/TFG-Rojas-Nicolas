"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Image from "next/image";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createBrowserClient } from "@supabase/ssr";

const registerSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[0-9]/, "Password must contain at least one number")
    .regex(/[^a-zA-Z0-9]/, "Password must contain at least one special character"),
});

type RegisterFormValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);
  const [isMicrosoftLoading, setIsMicrosoftLoading] = useState(false);

  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    mode: "onBlur",
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const supabase = createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );

  const onSubmit = async (data: RegisterFormValues) => {
    setIsLoading(true);
    try {
      const { error } = await supabase.auth.signUp({
        email: data.email,
        password: data.password,
      });

      if (error) {
        form.setError("root", { message: error.message });
      } else {
        console.log("Success! Please check your email.");
      }
    } catch (error) {
      console.error("Unexpected error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOAuthLogin = async (provider: "google" | "azure") => {
    if (provider === "google") setIsGoogleLoading(true);
    if (provider === "azure") setIsMicrosoftLoading(true);

    try {
      await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });
    } catch (error) {
      console.error(`Error with ${provider} login:`, error);
    } finally {
      setIsGoogleLoading(false);
      setIsMicrosoftLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white flex flex-col md:flex-row font-sans">
      {/* Sección Izquierda - Imagen */}
      <div className="hidden md:flex md:w-1/2 lg:w-[55%] relative flex-col justify-end p-12 bg-neutral-900 border-r border-[#1f1f1f] overflow-hidden">
        <div className="absolute inset-0 z-0">
          <Image
            src="/fondo-nyro-ascii.png"
            alt="Fondo Synthesis"
            fill
            className="object-cover"
            priority
          />
        </div>
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent z-10" />
        <div className="relative z-20 max-w-md">
          <h1 className="text-3xl lg:text-4xl font-medium tracking-tight mb-3">
            Your gateway to business intelligence evolution.
          </h1>
          <p className="text-gray-400 text-lg mb-8">
            Stop guessing. Start leading.
          </p>
          <div className="flex items-center text-sm text-gray-500">
            <span className="text-[#a3b899] mr-2">Synthesis</span>
            — Data With Purpose.
          </div>
        </div>
      </div>

      {/* Sección Derecha - Formulario */}
      <div className="flex-1 flex flex-col justify-center px-6 py-12 md:px-12 lg:px-24">
        <div className="max-w-[440px] w-full mx-auto">
          <div className="mb-10">
            <h2 className="text-2xl font-medium mb-3">Create your account</h2>
            <p className="text-gray-400 text-sm">
              Join the place for data driven leaders.
            </p>
          </div>

          {/* Botones SSO */}
          <div className="space-y-3 mb-8">
            <Button
              variant="outline"
              type="button"
              className="w-full bg-transparent border-[#2a2a2a] text-white hover:bg-[#1a1a1a] hover:text-white h-11"
              onClick={() => handleOAuthLogin("google")}
              disabled={isGoogleLoading || isMicrosoftLoading || isLoading}
            >
              {isGoogleLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                  <path d="M1 1h22v22H1z" fill="none" />
                </svg>
              )}
              Continue with Google
            </Button>
            <Button
              variant="outline"
              type="button"
              className="w-full bg-transparent border-[#2a2a2a] text-white hover:bg-[#1a1a1a] hover:text-white h-11"
              onClick={() => handleOAuthLogin("azure")}
              disabled={isGoogleLoading || isMicrosoftLoading || isLoading}
            >
              {isMicrosoftLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <svg className="mr-2 h-4 w-4" viewBox="0 0 21 21">
                  <path fill="#f25022" d="M0 0h10v10H0z" />
                  <path fill="#7fba00" d="M11 0h10v10H11z" />
                  <path fill="#00a4ef" d="M0 11h10v10H0z" />
                  <path fill="#ffb900" d="M11 11h10v10H11z" />
                </svg>
              )}
              Continue with Microsoft
            </Button>
          </div>

          <div className="relative mb-8">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-[#2a2a2a]" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-[#0A0A0A] px-2 text-gray-500">
                Or continue with email
              </span>
            </div>
          </div>

          {form.formState.errors.root && (
            <div className="mb-4 p-3 rounded bg-red-500/10 border border-red-500/20 text-red-500 text-sm">
              {form.formState.errors.root.message}
            </div>
          )}

          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-gray-400 font-normal">
                Email address <span className="text-gray-600">*</span>
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="e.g. andrew@example.com"
                className="bg-[#111] border-[#2a2a2a] focus-visible:ring-[#B8DB00] focus-visible:border-[#B8DB00] text-white placeholder:text-gray-600 h-11"
                {...form.register("email")}
              />
              {form.formState.errors.email && (
                <p className="text-red-400 text-xs">
                  {form.formState.errors.email.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-gray-400 font-normal">
                Password <span className="text-gray-600">*</span>
              </Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••••••••••"
                  className="bg-[#111] border-[#2a2a2a] focus-visible:ring-[#B8DB00] focus-visible:border-[#B8DB00] text-white placeholder:text-gray-600 h-11 pr-10"
                  {...form.register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
              {form.formState.errors.password && (
                <p className="text-red-400 text-xs">
                  {form.formState.errors.password.message}
                </p>
              )}
              <p className="text-xs text-gray-600 mt-2">
                Password must be at least 8 characters, including a number and a special character.
              </p>
            </div>

            <Button
              type="submit"
              disabled={isLoading || isGoogleLoading || isMicrosoftLoading}
              className="w-full bg-[#B7FF1F] hover:bg-[#FFFFFF] text-black font-semibold h-11 transition-colors duration-200 shadow-sm"
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create account
            </Button>
          </form>

          <div className="mt-8 text-center text-sm text-gray-400">
            Already have an account?{" "}
            <a href="/login" className="text-white hover:underline">
              Log in
            </a>
          </div>

          <div className="mt-12 text-center text-xs text-gray-600">
            By creating an account, you agree to our{" "}
            <a href="#" className="underline">Terms of Service</a> and{" "}
            <a href="#" className="underline">Privacy Policy</a>.
          </div>
        </div>
      </div>
    </div>
  );
}
