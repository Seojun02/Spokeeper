import { ProgressFooter } from './components/ProgressFooter';
import { ReaderLayout } from './components/ReaderLayout';
import { TopBar } from './components/TopBar';

export default function App() {
  return (
    <div className="grid h-full grid-rows-[60px_minmax(0,1fr)_48px] bg-[#f2f1ec] text-[#20231f]">
      <TopBar />
      <ReaderLayout />
      <ProgressFooter />
    </div>
  );
}
