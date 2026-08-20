export interface SpeakerDSPStatus {
  enabled: boolean;
  profile?: string | null;
  speaker_node?: string | null;
  error?: string;
}

export interface ResumeFixStatus {
  applied: boolean;
  service_active?: boolean;
  service_enabled?: boolean;
  script_exists?: boolean;
  pci_device_exists?: boolean;
  error?: string;
}

export interface PlatformStatus {
  supported: boolean;
  reason?: string | null;
  os_id?: string;
  product?: string;
}

export interface StatusResponse {
  platform: PlatformStatus;
  speaker_dsp: SpeakerDSPStatus;
  resume_fix: ResumeFixStatus;
}

export interface FixResult {
  success: boolean;
  message?: string;
  error?: string;
  warning?: string;
  reboot_needed?: boolean;
  steps?: string[];
}

export interface ProfileOption {
  data: string;
  label: string;
}

export interface LoadingState {
  active: string | null;
  message: string;
}

export interface ResultMessage {
  key: string;
  text: string;
  type: "success" | "error";
}

export interface EQBand {
  label: string;
  freq: number;
  gain: number;
}
