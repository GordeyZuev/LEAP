import { Footer } from "@/components/layout/footer";

// Metadata is generated per token in `[token]/page.tsx` so a shared link
// previews with the recording's own name. Nothing static to set here.
export default function ShareLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="flex-1">{children}</div>
      <Footer variant="public" />
    </div>
  );
}
