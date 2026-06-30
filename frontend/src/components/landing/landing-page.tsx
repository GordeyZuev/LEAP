import { LandingNavbar } from "./landing-navbar";
import { LandingHero } from "./landing-hero";
import { LandingAudience } from "./landing-audience";
import { LandingHowItWorks } from "./landing-how-it-works";
import { LandingFeatures } from "./landing-features";
import { LandingCta } from "./landing-cta";

export function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <LandingNavbar />
      <main>
        <LandingHero />
        <LandingAudience />
        <LandingHowItWorks />
        <LandingFeatures />
      </main>
      <LandingCta />
    </div>
  );
}
