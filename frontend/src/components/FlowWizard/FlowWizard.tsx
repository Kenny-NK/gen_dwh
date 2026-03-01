/**
 * Flow wizard component with steps (T063).
 */

import React, { useState } from "react";
import { Button } from "../common/Button";

interface FlowWizardProps {
  steps: { label: string; component: React.ReactNode }[];
  onComplete: () => void;
  onCancel: () => void;
}

export function FlowWizard({ steps, onComplete, onCancel }: FlowWizardProps) {
  const [currentStep, setCurrentStep] = useState(0);

  const isLastStep = currentStep === steps.length - 1;

  return (
    <div>
      {/* Step indicators */}
      <div className="mb-8 flex items-center gap-2">
        {steps.map((step, i) => (
          <React.Fragment key={i}>
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${
                i <= currentStep
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 text-gray-500"
              }`}
            >
              {i + 1}
            </div>
            <span
              className={`text-sm ${
                i <= currentStep ? "text-blue-600" : "text-gray-400"
              }`}
            >
              {step.label}
            </span>
            {i < steps.length - 1 && (
              <div className={`h-0.5 flex-1 ${i < currentStep ? "bg-blue-600" : "bg-gray-200"}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Step content */}
      <div className="mb-8">{steps[currentStep].component}</div>

      {/* Navigation */}
      <div className="flex justify-between">
        <Button variant="secondary" onClick={currentStep === 0 ? onCancel : () => setCurrentStep((s) => s - 1)}>
          {currentStep === 0 ? "Отмена" : "Назад"}
        </Button>
        <Button onClick={isLastStep ? onComplete : () => setCurrentStep((s) => s + 1)}>
          {isLastStep ? "Завершить" : "Далее"}
        </Button>
      </div>
    </div>
  );
}
