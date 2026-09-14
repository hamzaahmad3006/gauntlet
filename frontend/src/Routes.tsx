import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Callback from "./Pages/Auth/Callback/Callback";
import Login from "./Pages/Auth/Login/Login";
import Calibration from "./Pages/Dashboard/Calibration/Calibration";
import CallDetail from "./Pages/Dashboard/CallDetail/CallDetail";
import Compare from "./Pages/Dashboard/Compare/Compare";
import Integrations from "./Pages/Dashboard/Integrations/Integrations";
import LiveRun from "./Pages/Dashboard/LiveRun/LiveRun";
import NewRun from "./Pages/Dashboard/NewRun/NewRun";
import Report from "./Pages/Dashboard/Report/Report";
import Results from "./Pages/Dashboard/Results/Results";
import Runs from "./Pages/Dashboard/Runs/Runs";
import Suites from "./Pages/Dashboard/Suites/Suites";
import TargetConfig from "./Pages/Dashboard/TargetConfig/TargetConfig";
import TalkToAgent from "./Pages/Dashboard/TalkToAgent/TalkToAgent";
import Targets from "./Pages/Dashboard/Targets/Targets";
import Landing from "./Pages/Frontend/Landing/Landing";
import PublicReport from "./Pages/Frontend/PublicReport/PublicReport";

/** Every route in the app. */
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/r/:token" element={<PublicReport />} />
      <Route path="/login" element={<Login />} />
      <Route path="/auth/callback" element={<Callback />} />
      <Route path="/dashboard" element={<Layout />}>
        <Route index element={<Targets />} />
        <Route path="targets/new" element={<TargetConfig />} />
        <Route path="targets/:id" element={<TargetConfig />} />
        <Route path="suites" element={<Suites />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/new" element={<NewRun />} />
        <Route path="runs/:id" element={<Results />} />
        <Route path="runs/:id/live" element={<LiveRun />} />
        <Route path="runs/:id/report" element={<Report />} />
        <Route path="calls/:id" element={<CallDetail />} />
        <Route path="compare" element={<Compare />} />
        <Route path="ci" element={<Integrations />} />
        <Route path="calibration" element={<Calibration />} />
        <Route path="talk" element={<TalkToAgent />} />
      </Route>
      <Route path="*" element={<Landing />} />
    </Routes>
  );
}
