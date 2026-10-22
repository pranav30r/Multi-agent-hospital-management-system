import { useEffect, useState, useCallback } from "react";
import { StatCard } from "./common/Components.jsx";
import { Icon } from "./common/Icon.jsx";
import { useDemo } from "../context/DemoContext.jsx";
import { getHospitalState } from "../api/dashboard.js";

function MetricCards() {
  const { demoMode, demoData } = useDemo();
  const [liveState, setLiveState] = useState(null);

  const fetchLive = useCallback(async () => {
    if (demoMode) return;
    try {
      const data = await getHospitalState();
      setLiveState(data);
    } catch {
      // Non-blocking fallback
    }
  }, [demoMode]);

  useEffect(() => {
    fetchLive();
    const handler = () => fetchLive();
    window.addEventListener("app:poll-refresh", handler);
    window.addEventListener("app:refresh-authoritative", handler);
    window.addEventListener("websocket:reconnected", handler);
    window.addEventListener("bed:updated", handler);
    window.addEventListener("patient:updated", handler);
    return () => {
      window.removeEventListener("app:poll-refresh", handler);
      window.removeEventListener("app:refresh-authoritative", handler);
      window.removeEventListener("websocket:reconnected", handler);
      window.removeEventListener("bed:updated", handler);
      window.removeEventListener("patient:updated", handler);
    };
  }, [fetchLive]);

  const icuVal = demoMode
    ? demoData.kpis.icuOccupancy
    : (liveState?.icu?.utilization_pct != null ? Math.round(liveState.icu.utilization_pct) : 0);

  const icuTrend = demoMode
    ? demoData.kpis.icuTrend
    : `${liveState?.icu?.occupied || 0}/${liveState?.icu?.total || 8} Beds`;

  const erQueue = demoMode
    ? demoData.kpis.erQueue
    : (liveState?.er?.active_patients || liveState?.patients?.active_encounters || 9);

  const pendingDecisions = demoMode
    ? demoData.kpis.pendingDecisions
    : (liveState?.approvals?.pending || 0);

  const availBeds = demoMode
    ? demoData.kpis.availableBeds
    : (liveState?.beds?.AVAILABLE != null ? liveState.beds.AVAILABLE : 44);

  const totalBeds = demoMode
    ? demoData.kpis.totalBeds
    : (liveState?.beds?.total || 44);

  return (
    <div className="metrics-grid-epic">
      <StatCard
        title="ICU Utilization"
        value={`${icuVal}%`}
        trend="up"
        trendValue={icuTrend}
        sparkline={[58, 62, 68, 65, 72, 79, icuVal]}
        icon={<Icon name="activity" size={16} />}
        caption={`${liveState?.icu?.occupied || (demoMode ? 12 : 0)} of ${liveState?.icu?.total || (demoMode ? 15 : 8)} ventilator beds engaged`}
      />

      <StatCard
        title="Emergency Queue"
        value={erQueue}
        unit="Patients"
        trend="down"
        trendValue="-2 this hr"
        sparkline={[16, 15, 14, 12, 11, 10, erQueue]}
        icon={<Icon name="users" size={16} />}
        caption="Average wait time: 14 mins"
      />

      <StatCard
        title="Actionable Decisions"
        value={pendingDecisions}
        unit="Pending"
        trend="up"
        trendValue={pendingDecisions > 0 ? "Action Required" : "Nominal"}
        sparkline={[1, 2, 4, 3, 5, 4, pendingDecisions]}
        icon={<Icon name="sparkles" size={16} />}
        caption={pendingDecisions > 0 ? "High-risk transfers awaiting MD sign-off" : "All clinical decisions resolved"}
      />

      <StatCard
        title="Available Capacity"
        value={availBeds}
        unit="Beds"
        trend="up"
        trendValue={`${availBeds} of ${totalBeds} open`}
        sparkline={[15, 16, 17, 18, 19, 20, availBeds]}
        icon={<Icon name="bed" size={16} />}
        caption="Across General, ICU & Pediatric"
      />
    </div>
  );
}

export default MetricCards;
