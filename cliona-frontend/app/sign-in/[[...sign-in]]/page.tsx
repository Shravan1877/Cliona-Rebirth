import { SignIn } from "@clerk/nextjs";
import { clerkAppearance } from "@/lib/clerk-appearance";

export default function SignInPage() {
  return (
    <div className="grid min-h-dvh place-items-center bg-background">
      <SignIn appearance={clerkAppearance} />
    </div>
  );
}
