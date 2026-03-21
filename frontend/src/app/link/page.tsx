import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { getUserSettings } from "@/lib/redis";
import { RepoLinker } from "@/components/RepoLinker";
import { DeviceCodeForm } from "@/components/DeviceCodeForm";

export default async function LinkPage() {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/api/auth/signin");
  }

  const settings = await getUserSettings(session.user.id);

  if (!settings?.repo) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="bg-card border border-border rounded-xl p-8 max-w-md w-full">
          <h2 className="text-lg font-bold text-bright mb-1">
            Link Repository First
          </h2>
          <p className="text-sub text-sm mb-4">
            You need to link a repository before you can connect a device.
          </p>
          <RepoLinker />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="bg-card border border-border rounded-xl p-8 max-w-md w-full">
        <h2 className="text-lg font-bold text-bright mb-1">
          Link Device
        </h2>
        <p className="text-sub text-sm mb-4">
          Enter the code shown on your uConsole to connect it to your account.
        </p>
        <DeviceCodeForm />
      </div>
    </div>
  );
}
