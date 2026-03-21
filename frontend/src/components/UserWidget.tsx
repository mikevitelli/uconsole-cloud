import type { Session } from "next-auth";

export function UserAvatar({
  session,
  size = "w-6 h-6",
}: {
  session: Session;
  size?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      {session.user?.image && (
        <img src={session.user.image} alt="" className={`${size} rounded-full`} />
      )}
      <span className="text-sm text-foreground hidden sm:inline">
        {session.user?.name}
      </span>
    </div>
  );
}
