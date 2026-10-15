import { Mail } from "lucide-react";

import { FeedbackForm } from "@/components/product-news/forms";
import { ProductNewsPage } from "@/components/product-news/public-page";

export default function ProductFeedbackPage() {
  return (
    <ProductNewsPage title="Contact & Feedback" description="Tell us what would make LEAP better.">
      <FeedbackForm />
      <a
        href="mailto:gordey.zuev@gmail.com"
        className="pressable mx-auto mt-5 flex w-fit items-center gap-2 rounded-xl border border-border px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-muted"
      >
        <Mail size={16} />
        Or write to us directly
      </a>
    </ProductNewsPage>
  );
}
