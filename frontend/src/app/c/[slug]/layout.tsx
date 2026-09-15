import { Footer } from "@/components/layout/footer";
import { PublicShareHeader } from "@/components/share/public-share-header";

export default function ChannelPublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <PublicShareHeader />
      <div className="flex-1">{children}</div>
      <Footer variant="public" />
    </div>
  );
}
