import { SignedIn, SignedOut, RedirectToSignIn } from "@clerk/nextjs";
import { Assistant } from "./assistant";

export default function Home() {
  return (
    <>
      <SignedIn>
        <Assistant />
      </SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </>
  );
}
