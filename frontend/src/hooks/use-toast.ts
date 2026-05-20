import { useCallback, useRef, useState } from "react";
import { type ToastType } from "@/components/ui/toast";

export interface ToastState {
  type: ToastType;
  msg: string;
  serial: number;
  exiting: boolean;
}

const ANIM_OUT = 150;
let globalSerial = 0;

export function useToast(defaultMs = 4000) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exitRef  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (exitRef.current)  clearTimeout(exitRef.current);
    setToast((s) => (s ? { ...s, exiting: true } : null));
    exitRef.current = setTimeout(() => setToast(null), ANIM_OUT);
  }, []);

  const show = useCallback(
    (type: ToastType, msg: string, ms?: number) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (exitRef.current)  clearTimeout(exitRef.current);
      const serial = ++globalSerial;
      const duration = ms ?? defaultMs;
      setToast({ type, msg, serial, exiting: false });
      timerRef.current = setTimeout(() => {
        setToast((s) => (s?.serial === serial ? { ...s, exiting: true } : s));
        exitRef.current = setTimeout(
          () => setToast((s) => (s?.serial === serial ? null : s)),
          ANIM_OUT,
        );
      }, duration - ANIM_OUT);
    },
    [defaultMs],
  );

  return { toast, show, dismiss };
}
