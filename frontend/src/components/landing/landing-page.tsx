import { LandingNavbar } from "./landing-navbar";
import { LandingHero } from "./landing-hero";
import { LandingAudience } from "./landing-audience";
import { LandingHowItWorks } from "./landing-how-it-works";
import { LandingFeatures } from "./landing-features";
import { LandingCta } from "./landing-cta";

export function LandingPage() {
  return (
    <div className="theme-light min-h-screen bg-background text-foreground">
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
