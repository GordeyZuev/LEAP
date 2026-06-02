/** Shared Tailwind classes for resource filter toolbars (recordings, presets, …). */

export const FILTER_CARD =
  "rounded-2xl border border-[#D9D9D9]/90 bg-white shadow-sm p-4 sm:p-5 mb-6 space-y-5 overflow-visible";

export const FILTER_LABEL = "block text-xs font-medium text-gray-500 mb-1.5";

// All controls share one height (2.875rem = 46px) so they line up exactly with
// the segmented toggle group (FILTER_SEGMENT_WRAP): its py-2 buttons (36px) plus
// the wrap's p-1 (8px) and 1px border on each side total 46px. Keep these in sync.
export const FILTER_CONTROL =
  "w-full min-h-[2.875rem] px-3 py-2 rounded-xl border border-[#D9D9D9] bg-white text-sm text-gray-900 outline-none transition-colors focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10";

export const FILTER_SELECT =
  "w-full min-h-[2.875rem] pl-3 pr-8 py-2 rounded-xl border border-[#D9D9D9] bg-white text-sm font-medium text-gray-700 outline-none transition-colors focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 appearance-none";

/** Segmented toggle group (mapping / include flags). */
export const FILTER_SEGMENT_WRAP =
  "flex w-full rounded-xl border border-[#D9D9D9] bg-gray-50 p-1 gap-0.5";

export const FILTER_SEGMENT_BTN =
  "flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-center text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#224C87]/25";

export const FILTER_SEGMENT_ACTIVE = "bg-white text-[#224C87] shadow-sm";

export const FILTER_SEGMENT_IDLE = "text-gray-500 hover:text-gray-700";
