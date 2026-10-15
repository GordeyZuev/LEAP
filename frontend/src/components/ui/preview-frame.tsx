import { frameAt, type PreviewFrame } from "@/hooks/use-video-previews";

export function PreviewFrameImage({ frames, time, className = "" }: {
  frames: PreviewFrame[] | undefined;
  time: number;
  className?: string;
}) {
  const frame = frameAt(frames, time);
  if (!frame) return null;
  return (
    <span aria-hidden="true" className={`block h-9 w-16 shrink-0 overflow-hidden rounded bg-muted ${className}`}>
      <span
        className="block origin-top-left"
        style={{
          width: frame.width,
          height: frame.height,
          transform: `scale(${64 / frame.width})`,
          backgroundImage: `url("${frame.image}")`,
          backgroundPosition: `-${frame.x}px -${frame.y}px`,
          backgroundRepeat: "no-repeat",
        }}
      />
    </span>
  );
}
