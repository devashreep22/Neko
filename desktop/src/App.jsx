import Pet from "./components/Pet";

export default function App() {
  return (
    <div
      className="w-screen h-screen flex items-center justify-center bg-transparent"
      style={{ WebkitAppRegion: "drag" }}
    >
      <Pet />
    </div>
  );
}