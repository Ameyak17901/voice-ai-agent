import React, { useEffect, useRef } from 'react';

export default function VisualizerCanvas({ isConnected, isSpeaking, micAnalyser, playbackAnalyser }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationId = null;
    let phase = 0;
    let energy = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };

    resize();
    window.addEventListener('resize', resize);

    const dataArray = new Uint8Array(128);

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Measure audio energy from active analyser
      let currentAudioEnergy = isConnected ? 0.15 : 0.04;
      const activeAnalyser = isSpeaking ? playbackAnalyser : micAnalyser;

      if (activeAnalyser) {
        activeAnalyser.fftSize = 256;
        activeAnalyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        currentAudioEnergy = Math.min(1.0, Math.max(0.1, avg / 120.0));
      }

      energy += (currentAudioEnergy - energy) * 0.15;
      phase += 0.03 + energy * 0.05;

      let color1 = 'rgba(99, 102, 241, 0.4)';
      let color2 = 'rgba(6, 182, 212, 0.7)';
      let color3 = 'rgba(168, 85, 247, 0.6)';

      if (isSpeaking) {
        color1 = 'rgba(168, 85, 247, 0.5)';
        color2 = 'rgba(236, 72, 153, 0.8)';
        color3 = 'rgba(99, 102, 241, 0.7)';
      } else if (isConnected) {
        color1 = 'rgba(6, 182, 212, 0.5)';
        color2 = 'rgba(99, 102, 241, 0.85)';
        color3 = 'rgba(16, 185, 129, 0.7)';
      }

      const drawWave = (freq, amp, p, color, lw) => {
        ctx.beginPath();
        ctx.lineWidth = lw;
        ctx.strokeStyle = color;
        for (let x = 0; x <= width; x += 3) {
          const normX = x / width;
          const envelope = Math.sin(normX * Math.PI);
          const y = centerY + Math.sin(normX * freq * Math.PI * 2 + p) * amp * envelope;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      };

      drawWave(3, 25 + energy * 55, phase, color1, 2);
      drawWave(2, 18 + energy * 45, phase * 1.3, color2, 2.5);
      drawWave(4, 12 + energy * 35, phase * 0.8, color3, 1.5);

      animationId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', resize);
    };
  }, [isConnected, isSpeaking, micAnalyser, playbackAnalyser]);

  return <canvas ref={canvasRef} className="waveform-canvas" />;
}
