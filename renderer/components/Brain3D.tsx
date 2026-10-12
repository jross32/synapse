import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import type { NavigationIntent } from '@shared/nav';
import './brain-3d.css';

type Area = { name: string; position: [number, number, number]; route: NavigationIntent };
const regions: Area[] = [
  { name: 'AI Workforce', position: [-1.15, 1.0, 0.9], route: { page: 'ai-coding', section: 'sessions' } },
  { name: 'Shared Realm', position: [1.1, 0.75, 1.0], route: { page: 'apps', section: 'projects' } },
  { name: 'My Apps', position: [-0.5, -0.65, 1.5], route: { page: 'apps', section: 'projects' } },
  { name: 'Devices', position: [1.15, -0.35, 0.95], route: { page: 'settings' } },
  { name: 'System Health', position: [0, 1.45, 0.25], route: { page: 'trace' } },
];
const hint = 'Drag to rotate · Hold Ctrl while scrolling to zoom · Select a glowing node';
type Props = { activeCount: number; onNavigate: (intent: NavigationIntent) => void };

export function Brain3D({ activeCount, onNavigate }: Props): JSX.Element {
  const canvasRef = useRef<HTMLDivElement>(null);
  const navigateRef = useRef(onNavigate);
  const activeRef = useRef(activeCount);
  const invalidateRef = useRef<(() => void) | null>(null);
  const resetRef = useRef<(() => void) | null>(null);
  const [selected, setSelected] = useState(hint);
  const [available, setAvailable] = useState(true);

  useEffect(() => { navigateRef.current = onNavigate; }, [onNavigate]);
  useEffect(() => {
    activeRef.current = activeCount;
    invalidateRef.current?.();
  }, [activeCount]);

  useEffect(() => {
    const host = canvasRef.current;
    if (!host) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reduced = motion.matches;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    } catch {
      setAvailable(false);
      setSelected('3D graphics unavailable — use the region buttons below');
      return;
    }
    setAvailable(true);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const canvas = renderer.domElement;
    canvas.setAttribute('aria-hidden', 'true');
    host.appendChild(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);
    scene.add(new THREE.HemisphereLight(0xa4dcff, 0x171331, 1.8));
    const cyan = new THREE.DirectionalLight(0x67e8ff, 3.2);
    cyan.position.set(-3, 3, 4);
    scene.add(cyan);
    const violet = new THREE.DirectionalLight(0x9c70ff, 2.8);
    violet.position.set(3, 1, -2);
    scene.add(violet);
    const group = new THREE.Group();
    group.rotation.set(0.08, -0.25, -0.025);
    scene.add(group);

    // Sculpt each anatomical mass independently, preserving the central longitudinal fissure.
    // The multi-frequency displaced surface is true 3D geometry, not a flat image or shader illusion.
    const fold = (x: number, y: number, z: number): number => {
      const sulci = Math.pow(Math.abs(Math.sin(y * 17 + Math.sin(z * 9) * 1.9 + Math.cos(x * 6))), 9);
      const secondary = Math.pow(Math.abs(Math.sin(z * 23 + x * 11 + Math.sin(y * 8))), 12);
      const tertiary = Math.sin(x * 34 + y * 21) * Math.cos(z * 27 - x * 13);
      return 1 + 0.022 * tertiary + 0.026 * secondary - 0.11 * sulci;
    };
    const cortexGeometry = new THREE.SphereGeometry(1, 144, 100);
    const vertices = cortexGeometry.getAttribute('position');
    for (let i = 0; i < vertices.count; i++) {
      const x = vertices.getX(i), y = vertices.getY(i), z = vertices.getZ(i);
      const radius = fold(x, y, z);
      vertices.setXYZ(i, x * radius, y * radius, z * radius);
    }
    cortexGeometry.computeVertexNormals();
    const cortexMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x225b99, metalness: 0.06, roughness: 0.29, clearcoat: 0.68, clearcoatRoughness: 0.24,
      transmission: 0.13, thickness: 0.55, emissive: 0x113b76, emissiveIntensity: 0.55,
      transparent: true, opacity: 0.94,
    });
    const rimMaterial = new THREE.ShaderMaterial({
      uniforms: { glowColor: { value: new THREE.Color(0x69cfff) } },
      vertexShader: `varying vec3 viewNormal; varying vec3 viewDirection;
        void main() { vec4 viewPosition=modelViewMatrix*vec4(position,1.0);
          viewNormal=normalize(normalMatrix*normal); viewDirection=-viewPosition.xyz;
          gl_Position=projectionMatrix*viewPosition; }`,
      fragmentShader: `uniform vec3 glowColor; varying vec3 viewNormal; varying vec3 viewDirection;
        void main() { float rim=pow(1.0-max(dot(normalize(viewNormal),normalize(viewDirection)),0.0),2.4);
          gl_FragColor=vec4(glowColor,rim*0.48); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    // Distinct hemispheres, temporal lobes, wrinkled cerebellum and slender brainstem.
    const lobes: [number, number, number, number, number, number][] = [
      [-0.82, 0.27, 0, 0.79, 1.12, 1.12], [0.82, 0.27, 0, 0.79, 1.12, 1.12],
      [-0.85, -0.55, 0.48, 0.66, 0.49, 0.79], [0.85, -0.55, 0.48, 0.66, 0.49, 0.79],
      [0, -0.94, -0.69, 0.73, 0.42, 0.53], [0, -1.4, -0.49, 0.19, 0.44, 0.2],
    ];
    const cortexMeshes: THREE.Mesh[] = [];
    lobes.forEach(([x, y, z, sx, sy, sz], index) => {
      const mesh = new THREE.Mesh(cortexGeometry, index === 1 || index === 3
        ? cortexMaterial.clone() : cortexMaterial);
      if (index === 1 || index === 3) {
        (mesh.material as THREE.MeshPhysicalMaterial).color.setHex(0x503ca0);
        (mesh.material as THREE.MeshPhysicalMaterial).emissive.setHex(0x342078);
      }
      mesh.position.set(x, y, z);
      mesh.scale.set(sx, sy, sz);
      group.add(mesh);
      cortexMeshes.push(mesh);
      const rim = new THREE.Mesh(cortexGeometry, rimMaterial);
      rim.position.copy(mesh.position);
      rim.scale.copy(mesh.scale).multiplyScalar(1.008);
      group.add(rim);
    });

    // Fine illuminated surface fibers track the gyri; points sparkle like synapses.
    const fibers: number[] = [], neurons: number[] = [];
    for (const side of [-1, 1]) {
      for (let j = 0; j < 48; j++) {
        let previous: THREE.Vector3 | undefined;
        for (let i = 0; i <= 96; i++) {
          const angle = i / 96 * Math.PI * 2;
          const latitude = 0.08 + (j + 1) / 49 * (Math.PI - 0.16) + 0.035 * Math.sin(angle * 6 + j);
          const x = Math.sin(latitude) * Math.cos(angle);
          const y = Math.cos(latitude);
          const z = Math.sin(latitude) * Math.sin(angle);
          const radius = fold(x, y, z) + 0.018;
          const point = new THREE.Vector3(side * 0.82 + x * radius * 0.79, 0.27 + y * radius * 1.12, z * radius * 1.12);
          if (previous) fibers.push(previous.x, previous.y, previous.z, point.x, point.y, point.z);
          if (i % 11 === j % 11 && j % 2 === 0) neurons.push(point.x, point.y, point.z);
          previous = point;
        }
      }
    }
    const fiberGeometry = new THREE.BufferGeometry();
    fiberGeometry.setAttribute('position', new THREE.Float32BufferAttribute(fibers, 3));
    group.add(new THREE.LineSegments(fiberGeometry, new THREE.LineBasicMaterial({
      color: 0x70d5ff, transparent: true, opacity: 0.42, depthWrite: false,
    })));
    const neuronGeometry = new THREE.BufferGeometry();
    neuronGeometry.setAttribute('position', new THREE.Float32BufferAttribute(neurons, 3));
    group.add(new THREE.Points(neuronGeometry, new THREE.PointsMaterial({
      color: 0xb6f5ff, size: 0.042, transparent: true, opacity: 0.9, depthWrite: false,
    })));
    const markers: THREE.Mesh[] = [], halos: THREE.Mesh[] = [];
    const markerGeometry = new THREE.SphereGeometry(0.075, 12, 10);
    const haloGeometry = new THREE.SphereGeometry(0.15, 12, 10);
    regions.forEach((region, i) => {
      const color = i % 2 === 0 ? 0x83f3ff : 0xbf9aff;
      const marker = new THREE.Mesh(markerGeometry, new THREE.MeshBasicMaterial({ color }));
      marker.position.set(...region.position);
      marker.userData.region = region;
      group.add(marker);
      markers.push(marker);
      const halo = new THREE.Mesh(haloGeometry, new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.16, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      halo.position.copy(marker.position);
      group.add(halo);
      halos.push(halo);
    });
    for (const radius of [1.85, 2.08]) {
      const platform = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.009, 6, 96),
        new THREE.MeshBasicMaterial({ color: 0x4cafff, transparent: true, opacity: radius < 2 ? 0.35 : 0.12 }));
      platform.rotation.x = Math.PI / 2;
      platform.position.y = -1.83;
      scene.add(platform);
    }

    let pointerId: number | null = null;
    let moved = false, lastX = 0, lastY = 0, travel = 0;
    let zoom = 1, distance = 8, animation = 0, lastFrame = 0, phase = 0;
    let lastResetAt = 0;
    let inView = true, disposed = false, contextLost = false, dirty = true;
    const initialRotation = new THREE.Euler(0.08, -0.25, -0.025);
    let hovered: THREE.Mesh | undefined;
    let pointerNear: THREE.Vector2 | null = null;
    const ray = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const canRender = (): boolean => !disposed && !contextLost && inView && !document.hidden;
    const tick = (now: number): void => {
      animation = 0;
      if (!canRender()) return;
      // Limit GPU work to 30fps while keeping pointer updates immediate.
      if (dirty || reduced || now - lastFrame >= 1000 / 30) {
        const delta = lastFrame ? Math.min((now - lastFrame) / 1000, 0.05) : 0;
        lastFrame = now;
        if (!reduced) {
          phase += delta;
          if (pointerId === null && now - lastResetAt > 800) group.rotation.y += delta * 0.055;
        }
        markers.forEach((marker, i) => {
          const pulse = !reduced && activeRef.current > 0 ? Math.sin(phase * 2.2 + i * 0.7) * 0.08 : 0;
          const base = new THREE.Vector3(...regions[i].position);
          group.updateMatrixWorld(true);
          const world = base.clone().applyMatrix4(group.matrixWorld).project(camera);
          const proximity = pointerNear && !reduced && pointerId === null ? Math.pow(Math.max(0, 1 - Math.hypot(world.x - pointerNear.x, world.y - pointerNear.y) / 0.5), 2) : 0;
          const target = base.clone();
          if (pointerNear && proximity > 0) {
            const depth = base.clone().applyMatrix4(group.matrixWorld).project(camera).z;
            const worldTarget = new THREE.Vector3(world.x + (pointerNear.x - world.x) * proximity * 0.55, world.y + (pointerNear.y - world.y) * proximity * 0.55, depth).unproject(camera);
            target.copy(group.worldToLocal(worldTarget));
          }
          marker.position.lerp(target, reduced ? 1 : 0.17);
          marker.scale.setScalar(1 + pulse + proximity * 1.7 + (marker === hovered ? 0.3 : 0));
          halos[i].position.copy(marker.position);
          halos[i].scale.setScalar(1 + pulse * 1.5 + proximity * 2.4);
        });
        renderer.render(scene, camera);
        host.dataset.frame = String(Number(host.dataset.frame || 0) + 1);
        host.dataset.view = [group.rotation.x, group.rotation.y, group.rotation.z, zoom].map(value => value.toFixed(5)).join(',');
        dirty = false;
      }
      if (!reduced) animation = requestAnimationFrame(tick);
    };
    const invalidate = (): void => {
      dirty = true;
      if (!animation && canRender()) animation = requestAnimationFrame(tick);
    };
    invalidateRef.current = invalidate;
    const suspend = (): void => {
      cancelAnimationFrame(animation);
      animation = 0;
      lastFrame = 0;
    };
    const pick = (event: PointerEvent): THREE.Mesh | undefined => {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      scene.updateMatrixWorld(true);
      ray.setFromCamera(pointer, camera);
      const magnet = markers.map(marker => ({marker, point: marker.getWorldPosition(new THREE.Vector3()).project(camera)})).map(x => ({...x, distance: Math.hypot((x.point.x-pointer.x)*rect.width/2,(x.point.y-pointer.y)*rect.height/2)})).filter(x => x.point.z >= -1 && x.point.z <= 1 && x.distance < Math.max(28,Math.min(rect.width,rect.height)*.085)).sort((a,b)=>a.distance-b.distance)[0];
      if (magnet) return magnet.marker;
      const nearest = ray.intersectObjects([...markers, ...cortexMeshes], false)[0]?.object;
      return nearest instanceof THREE.Mesh && markers.includes(nearest) ? nearest : undefined;
    };
    const down = (event: PointerEvent): void => {
      if (!event.isPrimary || event.button !== 0 || pointerId !== null) return;
      pointerId = event.pointerId;
      moved = false;
      travel = 0;
      lastX = event.clientX;
      lastY = event.clientY;
      canvas.setPointerCapture(event.pointerId);
      host.dataset.dragging = 'true';
    };
    const move = (event: PointerEvent): void => {
      if (pointerId === null) {
        const rect = canvas.getBoundingClientRect();
        pointerNear = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
        const next = pick(event);
        if (next !== hovered) {
          hovered = next;
          host.dataset.hovered = String(Boolean(next));
          invalidate();
        }
        if (!reduced) invalidate();
        return;
      }
      if (event.pointerId !== pointerId) return;
      const dx = event.clientX - lastX, dy = event.clientY - lastY;
      travel += Math.hypot(dx, dy);
      moved = travel > 5;
      group.rotation.y += dx * 0.009;
      group.rotation.x = THREE.MathUtils.clamp(group.rotation.x + dy * 0.007, -0.85, 0.85);
      lastX = event.clientX;
      lastY = event.clientY;
      invalidate();
    };
    const cancel = (): void => {
      const captured = pointerId;
      pointerId = null;
      host.dataset.dragging = 'false';
      if (captured !== null && canvas.hasPointerCapture(captured)) canvas.releasePointerCapture(captured);
    };
    const up = (event: PointerEvent): void => {
      if (event.pointerId !== pointerId) return;
      const marker = !moved ? pick(event) : undefined;
      cancel();
      if (marker) {
        const region = marker.userData.region as Area;
        setSelected(region.name);
        marker.scale.setScalar(2.6);
        zoom = 0.82; camera.position.z = distance * zoom; invalidate();
        window.setTimeout(() => { if (!disposed) navigateRef.current(region.route); }, reduced ? 0 : 160);
      }
    };
    const leave = (): void => {
      pointerNear = null;
      hovered = undefined;
      host.dataset.hovered = 'false';
      invalidate();
    };
    const wheel = (event: WheelEvent): void => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const units = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? host.clientHeight : 1;
      zoom = THREE.MathUtils.clamp(zoom + event.deltaY * units * 0.0004, 0.82, 1.25);
      camera.position.z = distance * zoom;
      invalidate();
    };
    const reset = (): void => {
      group.rotation.copy(initialRotation);
      hovered = undefined;
      host.dataset.hovered = 'false';
      lastFrame = 0;
      lastResetAt = performance.now();
      zoom = 1;
      camera.position.z = distance;
      setSelected(hint);
      invalidate();
    };
    resetRef.current = reset;
    const resize = (): void => {
      const width = host.clientWidth, height = host.clientHeight;
      if (!width || !height) return;
      camera.aspect = width / height;
      distance = Math.max(5.6, 1.93 / (Math.tan(THREE.MathUtils.degToRad(20)) * camera.aspect));
      camera.position.set(0, 0.2, distance * zoom);
      camera.lookAt(0, -0.12, 0);
      camera.far = Math.max(50, distance * 2);
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      invalidate();
    };
    const motionChange = (): void => { reduced = motion.matches; suspend(); invalidate(); };
    const visibilityChange = (): void => { suspend(); cancel(); invalidate(); };
    const lost = (event: Event): void => {
      event.preventDefault();
      contextLost = true;
      suspend();
      cancel();
      setAvailable(false);
      setSelected('3D view paused — use the region buttons below');
    };
    const restored = (): void => {
      contextLost = false;
      setAvailable(true);
      setSelected(hint);
      resize();
    };
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', cancel);
    canvas.addEventListener('lostpointercapture', cancel);
    canvas.addEventListener('pointerleave', leave);
    canvas.addEventListener('wheel', wheel, { passive: false });
    canvas.addEventListener('dblclick', reset);
    canvas.addEventListener('webglcontextlost', lost);
    canvas.addEventListener('webglcontextrestored', restored);
    motion.addEventListener('change', motionChange);
    document.addEventListener('visibilitychange', visibilityChange);
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    const intersection = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      suspend();
      if (!inView) cancel();
      invalidate();
    });
    intersection.observe(host);
    resize();

    return () => {
      disposed = true;
      suspend();
      cancel();
      observer.disconnect();
      intersection.disconnect();
      motion.removeEventListener('change', motionChange);
      document.removeEventListener('visibilitychange', visibilityChange);
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      canvas.removeEventListener('pointercancel', cancel);
      canvas.removeEventListener('lostpointercapture', cancel);
      canvas.removeEventListener('pointerleave', leave);
      canvas.removeEventListener('wheel', wheel);
      canvas.removeEventListener('dblclick', reset);
      canvas.removeEventListener('webglcontextlost', lost);
      canvas.removeEventListener('webglcontextrestored', restored);
      invalidateRef.current = null;
      resetRef.current = null;
      // Dispose every unique resource once, including halos, neurons and rings.
      const geometries = new Set<THREE.BufferGeometry>();
      const materials = new Set<THREE.Material>();
      scene.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points) {
          geometries.add(object.geometry);
          const owned = Array.isArray(object.material) ? object.material : [object.material];
          owned.forEach(material => materials.add(material));
        }
      });
      geometries.forEach(geometry => geometry.dispose());
      materials.forEach(material => material.dispose());
      renderer.dispose();
      canvas.remove();
      delete host.dataset.dragging;
      delete host.dataset.hovered;
      delete host.dataset.frame;
    };
  }, []);

  return (
    <div className='synapse-brain-3d'>
      <div className='synapse-brain-3d__canvas' ref={canvasRef} role='img'
        aria-label='Interactive 3D Synapse brain. Drag to rotate, Control and scroll to zoom, or select the region dots to navigate.' />
      <div className='synapse-brain-3d__caption'>
        <span className='synapse-brain-3d__sr-only' role='status'>{selected}</span>
        {available && <button type='button' className='synapse-brain-3d__reset' aria-label='Reset brain view' title='Reset brain view' onClick={() => resetRef.current?.()}>
          <span aria-hidden='true'>↺</span>
        </button>}
      </div>
      <div className='synapse-brain-3d__regions' role='group' aria-label='Brain regions'>
        {regions.map(region => <button type='button' key={region.name} title={region.name} aria-label={`Open ${region.name}`} onClick={() => onNavigate(region.route)}>
          <span aria-hidden='true' />
        </button>)}
      </div>
    </div>
  );
}

