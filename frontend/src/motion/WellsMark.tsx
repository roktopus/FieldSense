import { useEffect, useRef } from "react";
import * as THREE from "three";

const targets = new Set<HTMLCanvasElement>();
let renderer: THREE.WebGLRenderer | null = null;
let scene: THREE.Scene | null = null;
let camera: THREE.PerspectiveCamera | null = null;
let raf = 0;
let reduce = false;
let head: THREE.Group | null = null;
let lamp: THREE.Mesh | null = null;

function drawTargets() {
  if (!renderer) return;
  const source = renderer.domElement;
  targets.forEach((canvas) => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  });
}

function tick() {
  if (!renderer || !scene || !camera || !head) return;
  if (!reduce) {
    const t = performance.now() * 0.001;
    head.rotation.y = Math.sin(t * 0.7) * 0.4;
    head.rotation.x = Math.sin(t * 1.15) * 0.06;
    if (lamp) {
      const mat = lamp.material as THREE.MeshStandardMaterial;
      mat.emissiveIntensity = 0.55 + Math.sin(t * 2.2) * 0.25;
    }
  }
  renderer.render(scene, camera);
  drawTargets();
  raf = !reduce && targets.size ? requestAnimationFrame(tick) : 0;
}

function ensure() {
  if (!renderer) {
    reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const buffer = document.createElement("canvas");
    renderer = new THREE.WebGLRenderer({
      canvas: buffer,
      alpha: true,
      antialias: true,
      preserveDrawingBuffer: true,
    });
    renderer.setPixelRatio(1);
    renderer.setSize(256, 256, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(28, 1, 0.1, 20);
    camera.position.set(0, 0.42, 2.55);
    camera.lookAt(0, 0.28, 0);
    scene.add(new THREE.AmbientLight(0xfff6ee, 0.75));
    const key = new THREE.DirectionalLight(0xfff1e4, 2.4);
    key.position.set(1.5, 3, 2);
    scene.add(key);

    const jacket = new THREE.MeshStandardMaterial({ color: 0x3a332c, metalness: 0.2, roughness: 0.6 });
    const hat = new THREE.MeshStandardMaterial({ color: 0xd4652f, metalness: 0.28, roughness: 0.4 });
    const face = new THREE.MeshStandardMaterial({ color: 0xe7d3b4, roughness: 0.55, metalness: 0.02 });
    const dark = new THREE.MeshStandardMaterial({ color: 0x1a1612, roughness: 0.4, metalness: 0.3 });
    const lampMat = new THREE.MeshStandardMaterial({
      color: 0xf6e7c1,
      emissive: 0xf6e7c1,
      emissiveIntensity: 0.7,
      roughness: 0.3,
    });

    const shoulders = new THREE.Mesh(new THREE.SphereGeometry(0.62, 28, 18, 0, Math.PI * 2, 0, Math.PI * 0.55), jacket);
    shoulders.scale.set(1.25, 0.62, 0.85);
    shoulders.position.y = -0.22;
    scene.add(shoulders);

    const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.2, 0.16, 16), jacket);
    collar.position.y = 0.12;
    scene.add(collar);

    head = new THREE.Group();
    head.position.y = 0.28;
    const skull = new THREE.Mesh(new THREE.SphereGeometry(0.36, 32, 24), face);
    skull.position.y = 0.22;
    const crown = new THREE.Mesh(new THREE.SphereGeometry(0.38, 28, 16, 0, Math.PI * 2, 0, Math.PI * 0.5), hat);
    crown.position.y = 0.34;
    const brim = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.035, 28), hat);
    brim.position.y = 0.32;
    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.07, 0.06), dark);
    visor.position.set(0, 0.2, 0.32);
    lamp = new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 10), lampMat);
    lamp.position.set(0.22, 0.48, 0.22);
    head.add(skull, crown, brim, visor, lamp);
    scene.add(head);
  }
  if (!raf) tick();
}

/** Shared 3D analyst mark. One WebGL buffer, painted onto each canvas. */
export function WellsMark({ size = "chat" }: { size?: "chat" | "hero" }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const dim = size === "hero" ? 220 : 96;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    targets.add(canvas);
    ensure();
    return () => {
      targets.delete(canvas);
      if (!targets.size) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    };
  }, []);

  return (
    <canvas
      ref={ref}
      width={dim}
      height={dim}
      className={size === "hero" ? "h-44 w-44 shrink-0" : "h-11 w-11 shrink-0"}
      aria-hidden
    />
  );
}
