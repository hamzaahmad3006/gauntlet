import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { CallDetail, Waveform } from "../../../api/types";

export function useCallDetail() {
  const { id } = useParams();
  const detail = useQuery({ queryKey: ["call", id], queryFn: () => api.get<CallDetail>(endpoints.call(id!)) });
  const waveform = useQuery({ queryKey: ["waveform", id], queryFn: () => api.get<Waveform>(endpoints.callWaveform(id!)) });
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const loadAudio = async () => {
    try {
      setAudioUrl(await api.blobUrl(endpoints.callAudio(id!)));
    } catch {
      setAudioError("audio unavailable — retention expired or upload failed");
    }
  };
  useEffect(() => () => { if (audioUrl) URL.revokeObjectURL(audioUrl); }, [audioUrl]);
  return { detail, waveform, audioUrl, audioError, loadAudio };
}
