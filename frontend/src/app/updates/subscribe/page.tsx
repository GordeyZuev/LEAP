import { SubscribeForm } from "@/components/product-news/forms";
import { ProductNewsPage } from "@/components/product-news/public-page";

export default function ProductNewsSubscribePage() {
  return (
    <ProductNewsPage title="Email updates" description="Occasional emails about major LEAP updates.">
      <SubscribeForm />
    </ProductNewsPage>
  );
}
