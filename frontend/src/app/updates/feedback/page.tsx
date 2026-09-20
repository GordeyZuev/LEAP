import { FeedbackForm } from "@/components/product-news/forms";
import { ProductNewsPage } from "@/components/product-news/public-page";

export default function ProductFeedbackPage() {
  return (
    <ProductNewsPage title="Share feedback" description="Tell us what would make LEAP better.">
      <FeedbackForm />
    </ProductNewsPage>
  );
}
