import { SignUp } from "@clerk/nextjs";
import { clerkAppearance } from "@/lib/clerk-appearance";

export default function SignUpPage() {
  return (
    <div className="grid min-h-dvh place-items-center bg-background">
      <SignUp appearance={clerkAppearance} />
    </div>
  );
}
