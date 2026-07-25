import { useEffect, useState } from "react";
import { useTranslation } from "../i18n";

const STEP_TIMINGS = [
  { delay: 0, duration: 4000 },      // analyzing
  { delay: 4000, duration: 8000 },    // writing
  { delay: 12000, duration: 6000 },   // polishing
];

export function ScriptGenerationProgress() {
  const { t } = useTranslation();
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    { label: t.script_step_analyzing, icon: "◉" },
    { label: t.script_step_writing, icon: "✎" },
    { label: t.script_step_polishing, icon: "✦" },
  ];

  useEffect(() => {
    const timers = STEP_TIMINGS.map((timing, idx) => {
      if (idx === 0) return null; // step 0 starts immediately
      return setTimeout(() => setActiveStep(idx), timing.delay);
    });
    return () => timers.forEach((t) => t && clearTimeout(t));
  }, []);

  return (
    <div className="py-10 flex flex-col items-center gap-8">
      {/* Pulsing icon */}
      <div className="relative">
        <div className="w-16 h-16 rounded-full bg-surface-light border border-border-subtle flex items-center justify-center">
          <span className="text-2xl text-cream animate-pulse">
            {steps[activeStep].icon}
          </span>
        </div>
        <span className="absolute -top-1 -right-1 flex h-4 w-4">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cream opacity-75" />
          <span className="relative inline-flex rounded-full h-4 w-4 bg-cream-dim" />
        </span>
      </div>

      {/* Steps */}
      <div className="flex items-center gap-3 sm:gap-4">
        {steps.map((step, idx) => {
          const isActive = idx === activeStep;
          const isDone = idx < activeStep;

          return (
            <div key={idx} className="flex items-center gap-3 sm:gap-4">
              {idx > 0 && (
                <div
                  className={`w-6 sm:w-10 h-px transition-colors duration-500 ${
                    isDone ? "bg-cream" : "bg-border-subtle"
                  }`}
                />
              )}
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm transition-all duration-500 ${
                    isActive
                      ? "bg-cream text-[#0C0C0C] scale-110"
                      : isDone
                        ? "bg-cream/20 text-cream"
                        : "bg-surface-light text-cream-muted"
                  }`}
                >
                  {isDone ? (
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    step.icon
                  )}
                </div>
                <span
                  className={`text-[11px] whitespace-nowrap transition-colors duration-500 ${
                    isActive ? "text-cream font-medium" : isDone ? "text-cream-dim" : "text-cream-muted"
                  }`}
                >
                  {step.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="w-48 h-1 bg-surface-light rounded-full overflow-hidden">
        <div
          className="h-full bg-cream rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${Math.min(100, ((activeStep + 1) / steps.length) * 90)}%`,
            animation: "pulse 2s ease-in-out infinite",
          }}
        />
      </div>
    </div>
  );
}
