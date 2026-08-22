import { FC } from "react";
import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  Spinner,
  ToggleField,
} from "@decky/ui";
import type {
  LoadingState,
  ResultMessage,
  ResumeFixStatus,
  VolumeButtonsStatus,
} from "./types";
import {
  applyResumeFix,
  revertResumeFix,
  recoverGamepad,
  applyVolumeButtons,
  revertVolumeButtons,
} from "./rpc";
import { InlineStatus } from "./InlineStatus";

export const FixesSection: FC<{
  resumeFix: ResumeFixStatus;
  setResumeFix: React.Dispatch<React.SetStateAction<ResumeFixStatus>>;
  volumeButtons: VolumeButtonsStatus;
  setVolumeButtons: React.Dispatch<React.SetStateAction<VolumeButtonsStatus>>;
  loading: LoadingState;
  setLoading: (l: LoadingState) => void;
  showResult: (key: string, text: string, type: "success" | "error") => void;
  result: ResultMessage | null;
  statusLoaded: boolean;
  refresh: () => Promise<void>;
}> = ({
  resumeFix,
  setResumeFix,
  volumeButtons,
  setVolumeButtons,
  loading,
  setLoading,
  showResult,
  result,
  statusLoaded,
  refresh,
}) => {
  const handleResumeFix = async (enabled: boolean) => {
    setLoading({
      active: "resume",
      message: enabled ? "Installing resume recovery..." : "Removing resume recovery...",
    });
    try {
      const res = enabled ? await applyResumeFix() : await revertResumeFix();
      if (res.success) {
        setResumeFix((prev) => ({ ...prev, applied: enabled }));
        showResult("resume", res.message || (enabled ? "Installed" : "Removed"), "success");
      } else {
        showResult("resume", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("resume", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  const handleVolumeButtons = async (enabled: boolean) => {
    setLoading({
      active: "volume",
      message: enabled ? "Enabling volume buttons..." : "Reverting volume buttons...",
    });
    try {
      const res = enabled ? await applyVolumeButtons() : await revertVolumeButtons();
      if (res.success) {
        setVolumeButtons((prev) => ({ ...prev, applied: enabled }));
        showResult("volume", res.message || (enabled ? "Enabled" : "Reverted"), "success");
      } else {
        showResult("volume", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("volume", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  const handleRecoverGamepad = async () => {
    setLoading({ active: "recoverGamepad", message: "Recovering gamepad (rebinding USB)..." });
    try {
      const res = await recoverGamepad();
      if (res.success) {
        showResult("recoverGamepad", res.message || "Recovered", "success");
      } else {
        showResult("recoverGamepad", res.error || "Failed", "error");
      }
    } catch (e) {
      showResult("recoverGamepad", `Error: ${e}`, "error");
    } finally {
      setLoading({ active: null, message: "" });
      refresh();
    }
  };

  return (
    <PanelSection title="Fixes">
      {!statusLoaded ? (
        <PanelSectionRow>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px 0" }}>
            <Spinner style={{ width: "16px", height: "16px" }} />
            <span style={{ fontSize: "12px", color: "#aaa" }}>Loading status...</span>
          </div>
        </PanelSectionRow>
      ) : (
        <>
          {/* Resume Recovery */}
          <PanelSectionRow>
            <ToggleField
              label="Resume Recovery"
              description={
                resumeFix.applied
                  ? "Active — gamepad recovers after sleep"
                  : "Fix gamepad not working after sleep"
              }
              checked={resumeFix.applied}
              disabled={loading.active === "resume"}
              onChange={handleResumeFix}
            />
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="resume" />

          {/* Volume Buttons */}
          <PanelSectionRow>
            <ToggleField
              label="Volume Buttons"
              description={
                volumeButtons.applied
                  ? "Active — InputPlumber no longer swallows the volume keys"
                  : "Fix the volume buttons doing nothing"
              }
              checked={volumeButtons.applied}
              disabled={loading.active === "volume"}
              onChange={handleVolumeButtons}
            />
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="volume" />

          {/* Manual Gamepad Recovery */}
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              description="Rebind the internal USB controller and restart InputPlumber if the gamepad is missing"
              disabled={loading.active === "recoverGamepad"}
              onClick={handleRecoverGamepad}
            >
              {loading.active === "recoverGamepad" ? "Recovering..." : "Recover Gamepad"}
            </ButtonItem>
          </PanelSectionRow>
          <InlineStatus loading={loading} result={result} section="recoverGamepad" />
        </>
      )}
    </PanelSection>
  );
};
