import type { Session } from "next-auth";
import Image from "next/image";

const SIZES: Record<string, number> = {
  "w-6 h-6": 24,
  "w-8 h-8": 32,
};

export function UserAvatar({
  session,
  size = "w-6 h-6",
}: {
  session: Session;
  size?: string;
}) {
  const px = SIZES[size] || 24;
  return (
    <div className="flex items-center gap-2">
      {session.user?.image && (
        <Image
          src={session.user.image}
          alt=""
          width={px}
          height={px}
          className={`${size} rounded-full`}
        />
      )}
      <span className="text-sm text-foreground hidden sm:inline">
        {session.user?.name}
      </span>
    </div>
  );
}
