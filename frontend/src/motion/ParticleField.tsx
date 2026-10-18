import { useEffect, useRef } from "react";

/** Night-lease backdrop: a low horizon and dust along the ground. */
export function ParticleField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const parent = canvas.parentElement;
    if (!parent) return;

    const dust = Array.from({ length: 16 }, () => ({
      x: Math.random(),
      y: 0.78 + Math.random() * 0.18,
      r: 0.6 + Math.random() * 1.1,
      v: 0.00004 + Math.random() * 0.00008,
      a: 0.12 + Math.random() * 0.2,
    }));
    let raf = 0;

    const draw = () => {
      const width = parent.clientWidth;
      const height = parent.clientHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(width * ratio));
      canvas.height = Math.max(1, Math.floor(height * ratio));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const ground = height * 0.86;
      const wash = ctx.createLinearGradient(0, ground - 40, 0, height);
      wash.addColorStop(0, "rgba(196, 122, 61, 0)");
      wash.addColorStop(1, "rgba(196, 122, 61, 0.05)");
      ctx.fillStyle = wash;
      ctx.fillRect(0, ground - 40, width, height - ground + 40);
      ctx.strokeStyle = "rgba(214, 168, 120, 0.16)";
      ctx.beginPath();
      ctx.moveTo(0, ground);
      ctx.lineTo(width, ground);
      ctx.stroke();

      for (const mote of dust) {
        if (!reduce) {
          mote.x += mote.v;
          if (mote.x > 1) mote.x = 0;
        }
        ctx.beginPath();
        ctx.fillStyle = `rgba(212, 154, 96, ${mote.a})`;
        ctx.arc(mote.x * width, mote.y * height, mote.r, 0, Math.PI * 2);
        ctx.fill();
      }
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    draw();
    const onResize = () => {
      if (reduce) draw();
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return <canvas ref={ref} className="pointer-events-none absolute inset-0 z-0" aria-hidden />;
}
