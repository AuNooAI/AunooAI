/**
 * Onboarding Wizard - Multi-step topic setup wizard
 */

import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { StepIndicator } from '../StepIndicator';
import { Step1ApiKeys } from './Step1ApiKeys';
import { Step2TopicSetup, type TopicSetupData } from './Step2TopicSetup';
import { Step3Keywords } from './Step3Keywords';
import { checkApiKeys } from '../../services/api';

interface OnboardingWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete?: () => void;
}

export function OnboardingWizard({ open, onOpenChange, onComplete }: OnboardingWizardProps) {
  const [currentStep, setCurrentStep] = useState(1);
  const [topicData, setTopicData] = useState<TopicSetupData | null>(null);
  const [suggestedKeywords, setSuggestedKeywords] = useState<any>(null);
  const [checkingKeys, setCheckingKeys] = useState(true);

  // Check existing keys when wizard opens
  useEffect(() => {
    if (open) {
      checkExistingKeys();
    }
  }, [open]);

  const checkExistingKeys = async () => {
    setCheckingKeys(true);
    try {
      const keyStatus = await checkApiKeys();

      // Check if all required keys are configured
      const allKeysPresent =
        (keyStatus.openai || keyStatus.anthropic || keyStatus.gemini) &&
        (keyStatus.newsapi || keyStatus.thenewsapi || keyStatus.newsdata) &&
        keyStatus.firecrawl;

      // If all keys are present, skip to Step 2
      if (allKeysPresent) {
        console.log('All API keys configured, skipping Step 1');
        setCurrentStep(2);
      } else {
        setCurrentStep(1);
      }
    } catch (error) {
      console.error('Error checking API keys:', error);
      setCurrentStep(1);
    } finally {
      setCheckingKeys(false);
    }
  };

  const handleStep1Next = () => {
    setCurrentStep(2);
  };

  const handleStep2Next = (data: TopicSetupData, keywords?: any) => {
    setTopicData(data);
    setSuggestedKeywords(keywords);
    setCurrentStep(3);
  };

  const handleStep2Back = () => {
    setCurrentStep(1);
  };

  const handleStep3Back = () => {
    setCurrentStep(2);
  };

  const handleComplete = () => {
    onOpenChange(false);
    setCurrentStep(1);
    setTopicData(null);
    setCheckingKeys(true);
    if (onComplete) {
      onComplete();
    }
  };

  const stepLabels = ['API Keys', 'Topic Setup', 'Keywords'];

  // Show loading state while checking keys
  if (checkingKeys && open) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Loading Onboarding</DialogTitle>
            <DialogDescription>
              Checking your API key configuration...
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto mb-4"></div>
              <p className="text-gray-700">Checking configuration...</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-center">Welcome to AuNoo AI</DialogTitle>
          <DialogDescription className="sr-only">
            Set up your AuNoo AI account and create your first topic
          </DialogDescription>
        </DialogHeader>

        <div className="mt-6">
          {/* Step Indicator */}
          <StepIndicator
            currentStep={currentStep}
            totalSteps={3}
            stepLabels={stepLabels}
          />

          {/* Step Content */}
          <div className="mt-8">
            {currentStep === 1 && <Step1ApiKeys onNext={handleStep1Next} />}

            {currentStep === 2 && (
              <Step2TopicSetup
                onNext={handleStep2Next}
                onBack={handleStep2Back}
              />
            )}

            {currentStep === 3 && topicData && (
              <Step3Keywords
                topicData={topicData}
                suggestedKeywords={suggestedKeywords}
                onBack={handleStep3Back}
                onComplete={handleComplete}
              />
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
