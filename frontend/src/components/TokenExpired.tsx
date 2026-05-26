import Image from "next/image";

interface TokenExpiredProps {
  title: string;
  message: string;
  signOutAction: () => void;
}

export function TokenExpired({ title, message, signOutAction }: TokenExpiredProps) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="flex flex-col items-center text-center">
        <div className="mb-8">
          <Image
            src="/uConsole-spin.gif"
            alt="ClockworkPi uConsole"
            width={200}
            height={200}
            unoptimized
          />
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3 bg-gradient-to-r from-bright via-accent to-bright bg-clip-text text-transparent">
          {title}
        </h1>
        <p className="text-sub text-sm sm:text-base max-w-md mb-8 leading-relaxed">
          {message}
        </p>
        <form action={signOutAction}>
          <button
            type="submit"
            className="flex items-center gap-2 bg-[#24292f] text-white font-medium rounded-lg px-5 py-2.5 text-sm hover:bg-[#32383f] hover:shadow-[0_0_12px_rgba(88,166,255,0.15)] transition-all cursor-pointer border border-[#3d444d]"
          >
            <Image src="/github-mark-white.svg" alt="" width={18} height={18} className="w-[18px] h-[18px]" />
            Sign in with GitHub
          </button>
        </form>
      </div>
    </div>
  );
}
