import svgPaths from "./svg-9kl2sgu8dk";

function TitleContainer() {
  return (
    <div className="content-stretch flex gap-[4px] items-center relative shrink-0 w-[558.5px]" data-name="Title Container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[26px] items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[24px] relative shrink-0 text-[16px] text-[rgba(0,7,27,0.5)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
          Explore
        </p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[26px] items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[24px] relative shrink-0 text-[16px] text-[rgba(0,7,27,0.5)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
          /
        </p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[26px] items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[24px] relative shrink-0 text-[16px] text-[rgba(0,7,20,0.62)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
          Strategic Recommendations
        </p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[26px] items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[24px] relative shrink-0 text-[16px] text-[rgba(0,7,27,0.5)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
          •
        </p>
      </div>
      <p className="font-['Inter:Regular',sans-serif] font-normal leading-[24px] not-italic relative shrink-0 text-[#1c2024] text-[16px] text-nowrap whitespace-pre">Current indicators and potential disruption scenarios</p>
    </div>
  );
}

function UserActions({ onConfigureClick }: { onConfigureClick?: () => void }) {
  return (
    <div className="content-stretch flex gap-[16px] items-center justify-end relative shrink-0" data-name="User Actions">
      <div className="relative shrink-0 size-[29px]" data-name="Bell">
        <div className="absolute inset-0" data-name="Vector">
          <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
            <g id="Vector"></g>
          </svg>
        </div>
        <div className="absolute bottom-[12.5%] left-[37.5%] right-[37.5%] top-3/4" data-name="Vector">
          <div className="absolute inset-[-27.59%_-13.79%]" style={{ "--stroke-0": "rgba(0, 0, 0, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 10 6">
              <path d={svgPaths.pb804e00} id="Vector" stroke="var(--stroke-0, black)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.607843" strokeWidth="2" />
            </svg>
          </div>
        </div>
        <div className="absolute bottom-1/4 left-[15.64%] right-[15.64%] top-[12.5%]" data-name="Vector">
          <div className="absolute inset-[-5.52%_-5.02%]" style={{ "--stroke-0": "rgba(0, 0, 0, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 22 21">
              <path d={svgPaths.p3ed1f280} id="Vector" stroke="var(--stroke-0, black)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.607843" strokeWidth="2" />
            </svg>
          </div>
        </div>
      </div>
      <div onClick={onConfigureClick} style={{cursor: onConfigureClick ? 'pointer' : 'default'}} className="box-border content-stretch flex gap-[8px] h-[32px] items-center justify-center px-[12px] py-0 relative rounded-[4px] shrink-0 transition" data-name="Button">
        <div aria-hidden="true" className="absolute border border-[rgba(0,6,46,0.2)] border-solid inset-0 pointer-events-none rounded-[4px]" />
        <div className="flex flex-col font-['Inter:Medium',sans-serif] font-medium justify-center leading-[0] not-italic relative shrink-0 text-[#60646c] text-[14px] text-nowrap">
          <p className="leading-[20px] whitespace-pre">Set up the topic</p>
        </div>
        <div className="bg-[rgba(255,255,255,0)] relative shrink-0 size-[16px]" data-name="Abstract / plus">
          <div className="absolute inset-[15%]" data-name="Vector">
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 12 12">
              <path clipRule="evenodd" d={svgPaths.p1b97200} fill="var(--fill-0, #60646C)" fillRule="evenodd" id="Vector" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function NavBar({ onConfigureClick }: { onConfigureClick?: () => void }) {
  return (
    <div className="bg-[rgba(255,255,255,0.8)] relative shrink-0 w-full" data-name="NavBar">
      <div aria-hidden="true" className="absolute border-[0px_0px_1px] border-[rgba(20,0,53,0.15)] border-solid inset-0 pointer-events-none" />
      <div className="flex flex-row items-center size-full">
        <div className="box-border content-stretch flex items-center justify-between px-[16px] py-[24px] relative w-full">
          <TitleContainer />
          <UserActions onConfigureClick={onConfigureClick} />
        </div>
      </div>
    </div>
  );
}

function ContentContainer() {
  return (
    <div className="box-border content-stretch flex gap-[8px] h-[28px] items-center justify-center p-[8px] relative rounded-[3px] shrink-0" data-name="content-container">
      <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[20px] relative shrink-0 text-[14px] text-[rgba(0,7,20,0.62)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
        AI Impact Timeline
      </p>
    </div>
  );
}

function ContentContainer1() {
  return (
    <div className="box-border content-stretch flex gap-[8px] h-[28px] items-center justify-center p-[8px] relative rounded-[3px] shrink-0" data-name="content-container">
      <p className="font-['Inter:Regular',sans-serif] font-normal leading-[20px] not-italic relative shrink-0 text-[14px] text-[rgba(0,7,20,0.62)] text-nowrap whitespace-pre">Trends Convergence</p>
    </div>
  );
}

function ContentContainer2() {
  return (
    <div className="box-border content-stretch flex gap-[8px] h-[28px] items-center justify-center p-[8px] relative rounded-[3px] shrink-0" data-name="content-container">
      <p className="font-['Inter:Regular',sans-serif] font-normal leading-[20px] not-italic relative shrink-0 text-[14px] text-[rgba(0,7,20,0.62)] text-nowrap whitespace-pre">{`Market Signals & Strategic Risks`}</p>
    </div>
  );
}

function ContentContainer3() {
  return (
    <div className="box-border content-stretch flex gap-[8px] h-[28px] items-center justify-center p-[8px] relative rounded-[3px] shrink-0" data-name="content-container">
      <p className="font-['Open_Sans:Medium',sans-serif] leading-[20px] not-italic relative shrink-0 text-[#1c2024] text-[14px] text-nowrap whitespace-pre">Strategic Recommendations</p>
    </div>
  );
}

function ContentContainer4() {
  return (
    <div className="box-border content-stretch flex gap-[8px] h-[28px] items-center justify-center p-[8px] relative rounded-[3px] shrink-0" data-name="content-container">
      <p className="font-['Inter:Regular',sans-serif] font-normal leading-[20px] not-italic relative shrink-0 text-[14px] text-[rgba(0,7,20,0.62)] text-nowrap whitespace-pre">Future Horizons</p>
    </div>
  );
}

function ContentContainer5() {
  return (
    <div className="content-stretch flex h-full items-center relative shrink-0" data-name="content-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex h-full items-center justify-center overflow-clip px-[8px] py-0 relative shrink-0" data-name="Trigger #1">
        <ContentContainer />
      </div>
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex h-full items-center justify-center overflow-clip px-[8px] py-0 relative shrink-0" data-name="Trigger #2">
        <ContentContainer1 />
      </div>
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex h-full items-center justify-center overflow-clip px-[8px] py-0 relative shrink-0" data-name="Trigger #3">
        <ContentContainer2 />
      </div>
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex h-full items-center justify-center overflow-clip px-[8px] py-0 relative shrink-0" data-name="Trigger #4">
        <div className="absolute bg-[#3358d4] bottom-0 h-[2px] left-0 right-0" data-name="indicator" />
        <ContentContainer3 />
      </div>
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex h-full items-center justify-center overflow-clip px-[8px] py-0 relative shrink-0" data-name="Trigger #5">
        <ContentContainer4 />
      </div>
    </div>
  );
}

function CardContainer() {
  return (
    <div className="content-stretch flex flex-col gap-[16px] items-center justify-center relative shrink-0" data-name="Card Container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[40px] items-start justify-center overflow-clip relative shrink-0" data-name="Tabs">
        <div className="absolute bg-[rgba(0,0,47,0.15)] bottom-0 h-px left-0 right-0" data-name="lock" />
        <ContentContainer5 />
      </div>
    </div>
  );
}

function Card() {
  return (
    <div className="bg-[rgba(255,255,255,0.8)] relative rounded-tl-[16px] rounded-tr-[16px] shrink-0 w-full" data-name="Card">
      <div className="box-border content-stretch flex flex-col gap-[24px] items-center justify-center overflow-clip pb-0 pt-[32px] px-0 relative rounded-[inherit] w-full">
        <CardContainer />
      </div>
      <div aria-hidden="true" className="absolute border-[1px_1px_0px] border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-tl-[16px] rounded-tr-[16px]" />
    </div>
  );
}

function Frame1000001995() {
  return (
    <div className="content-stretch flex gap-[10px] items-center justify-center relative shrink-0 size-[24px]">
      <div className="relative shrink-0 size-[18px]" data-name="Dot">
        <div className="absolute inset-[12.5%]" data-name="Vector">
          <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 14 14">
            <path d={svgPaths.p3efa9f80} fill="var(--fill-0, #00051D)" fillOpacity="0.454902" id="Vector" />
          </svg>
        </div>
      </div>
    </div>
  );
}

function CardContent({ topic }: { topic?: string }) {
  return (
    <div className="content-stretch flex gap-[4px] items-center relative shrink-0" data-name="Card Content">
      <Frame1000001995 />
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[24px] relative shrink-0 text-[16px] text-[rgba(0,5,29,0.45)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
          Topic:
        </p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Medium',sans-serif] leading-[24px] not-italic relative shrink-0 text-[#1c2024] text-[16px] text-nowrap whitespace-pre">{topic || 'No topic selected'}</p>
      </div>
    </div>
  );
}

function Frame1000001994({ topic }: { topic?: string }) {
  return (
    <div className="content-stretch flex flex-col gap-[4px] items-start justify-center relative shrink-0">
      <CardContent topic={topic} />
    </div>
  );
}

function CardContent1() {
  return (
    <div className="content-stretch flex gap-[4px] items-center relative shrink-0" data-name="Card Content">
      <div className="bg-[rgba(255,255,255,0)] relative shrink-0 size-[16px]" data-name="Dot">
        <div className="absolute inset-[34.167%]" data-name="Vector">
          <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 6 6">
            <path d={svgPaths.p7ba7a00} fill="var(--fill-0, #30A46C)" id="Vector" />
          </svg>
        </div>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Regular',sans-serif] font-normal leading-[24px] relative shrink-0 text-[16px] text-[rgba(0,5,29,0.45)] text-nowrap whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
          Last Updated
        </p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="Text">
        <p className="font-['Open_Sans:Medium',sans-serif] leading-[24px] not-italic relative shrink-0 text-[#1c2024] text-[16px] text-nowrap whitespace-pre">15.09.2025</p>
      </div>
    </div>
  );
}

function Frame1000001993() {
  return (
    <div className="content-stretch flex gap-[4px] items-center relative shrink-0">
      <CardContent1 />
      <div className="box-border content-stretch flex gap-[8px] h-[32px] items-center justify-center px-[12px] py-0 relative rounded-[4px] shrink-0" data-name="Action">
        <div className="flex flex-col font-['Inter:Regular',sans-serif] font-normal justify-center leading-[0] not-italic relative shrink-0 text-[#60646c] text-[14px] text-nowrap">
          <p className="leading-[20px] whitespace-pre">Reload</p>
        </div>
        <div className="bg-[rgba(255,255,255,0)] relative shrink-0 size-[16px]" data-name="Abstract / update">
          <div className="absolute inset-[6.88%_6.31%_6.88%_5.74%]" data-name="Vector">
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 15 14">
              <path clipRule="evenodd" d={svgPaths.p312c37f0} fill="var(--fill-0, #60646C)" fillRule="evenodd" id="Vector" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function CardContainer1() {
  return (
    <div className="content-stretch flex items-center justify-between relative shrink-0 w-full" data-name="Card Container">
      <Frame1000001994 />
      <Frame1000001993 />
    </div>
  );
}

function CardContent2() {
  return (
    <div className="content-stretch flex gap-[8px] items-center relative shrink-0" data-name="Card Content">
      <div className="bg-[rgba(0,71,241,0.07)] box-border content-stretch flex gap-[8px] h-[32px] items-center justify-center px-[12px] py-0 relative rounded-[4px] shrink-0" data-name="Button">
        <div className="bg-[rgba(255,255,255,0)] relative shrink-0 size-[16px]" data-name="Objects / gear">
          <div className="absolute inset-[4.33%]" data-name="Vector">
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 15 15">
              <path clipRule="evenodd" d={svgPaths.p18a79600} fill="var(--fill-0, #002BB7)" fillOpacity="0.772549" fillRule="evenodd" id="Vector" />
            </svg>
          </div>
        </div>
        <div className="flex flex-col font-['Inter:Medium',sans-serif] font-medium justify-center leading-[0] not-italic relative shrink-0 text-[14px] text-[rgba(0,43,183,0.77)] text-nowrap">
          <p className="leading-[20px] whitespace-pre">Configure</p>
        </div>
      </div>
    </div>
  );
}

function CardContent3() {
  return (
    <div className="content-stretch flex items-start relative shrink-0" data-name="Card Content">
      <div className="box-border content-stretch flex gap-[8px] h-[32px] items-center justify-center px-[12px] py-0 relative rounded-[4px] shrink-0" data-name="Button">
        <div className="relative shrink-0 size-[16px]" data-name="Format=Outline, Weight=Regular">
          <div className="absolute inset-[18.75%_12.5%]" data-name="Vector">
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 12 10">
              <path d={svgPaths.p2faa3000} fill="var(--fill-0, #002BB7)" fillOpacity="0.772549" id="Vector" />
            </svg>
          </div>
        </div>
        <div className="flex flex-col font-['Inter:Regular',sans-serif] font-normal justify-center leading-[0] not-italic relative shrink-0 text-[14px] text-[rgba(0,43,183,0.77)] text-nowrap">
          <p className="leading-[20px] whitespace-pre">Columns</p>
        </div>
      </div>
      <div className="box-border content-stretch flex gap-[8px] h-[32px] items-center justify-center px-[12px] py-0 relative rounded-[4px] shrink-0" data-name="Button">
        <div className="bg-[rgba(255,255,255,0)] relative shrink-0 size-[16px]" data-name="Abstract / download">
          <div className="absolute inset-[7%_13.33%_6.67%_13.33%]" data-name="Vector">
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 12 14">
              <path clipRule="evenodd" d={svgPaths.p340c5f80} fill="var(--fill-0, #002BB7)" fillOpacity="0.772549" fillRule="evenodd" id="Vector" />
            </svg>
          </div>
        </div>
        <div className="flex flex-col font-['Inter:Regular',sans-serif] font-normal justify-center leading-[0] not-italic relative shrink-0 text-[14px] text-[rgba(0,43,183,0.77)] text-nowrap">
          <p className="leading-[20px] whitespace-pre">Image</p>
        </div>
      </div>
      <div className="box-border content-stretch flex gap-[8px] h-[32px] items-center justify-center px-[12px] py-0 relative rounded-[4px] shrink-0" data-name="Button">
        <div className="bg-[rgba(255,255,255,0)] relative shrink-0 size-[16px]" data-name="Abstract / download">
          <div className="absolute inset-[7%_13.33%_6.67%_13.33%]" data-name="Vector">
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 12 14">
              <path clipRule="evenodd" d={svgPaths.p340c5f80} fill="var(--fill-0, #002BB7)" fillOpacity="0.772549" fillRule="evenodd" id="Vector" />
            </svg>
          </div>
        </div>
        <div className="flex flex-col font-['Inter:Regular',sans-serif] font-normal justify-center leading-[0] not-italic relative shrink-0 text-[14px] text-[rgba(0,43,183,0.77)] text-nowrap">
          <p className="leading-[20px] whitespace-pre">PDF</p>
        </div>
      </div>
    </div>
  );
}

function CardContent4() {
  return (
    <div className="content-stretch flex items-start justify-between relative shrink-0 w-full" data-name="Card Content">
      <CardContent2 />
      <CardContent3 />
    </div>
  );
}

function Frame1000001912() {
  return (
    <div className="content-stretch flex items-center justify-between relative shrink-0 w-full">
      <div className="flex flex-col font-['Inter:Bold',sans-serif] font-bold justify-center leading-[0] not-italic relative shrink-0 text-[#1c2024] text-[18px] text-nowrap tracking-[-0.04px]">
        <p className="leading-[26px] whitespace-pre">{`NEAR-TERM `}</p>
      </div>
      <div className="relative rounded-[8px] shrink-0 size-[40px]" data-name="Target">
        <div className="absolute inset-0" data-name="Vector">
          <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
            <g id="Vector"></g>
          </svg>
        </div>
        <div className="absolute bottom-1/2 left-1/2 right-[12.5%] top-[12.5%]" data-name="Vector">
          <div className="absolute inset-[-6.667%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 17 17">
              <path d="M1 16L16 1" id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
        <div className="absolute inset-[12.55%_12.48%_12.55%_12.61%]" data-name="Vector">
          <div className="absolute inset-[-3.34%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
              <path d={svgPaths.p1db97400} id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
        <div className="absolute inset-[31.26%_31.24%_31.24%_31.26%]" data-name="Vector">
          <div className="absolute inset-[-6.67%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 17 17">
              <path d={svgPaths.p34550b80} id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame1000001916() {
  return (
    <div className="content-stretch flex flex-col font-['Inter:Regular',sans-serif] font-normal gap-[12px] items-start leading-[0] not-italic relative shrink-0 text-[#1c2024] text-[16px] w-full">
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Focus on sustainable AI investments</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Prepare for market volatility</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Secure infrastructure partnerships</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Avoid AGI speculation</p>
      </div>
    </div>
  );
}

function Frame1000001752() {
  return (
    <div className="bg-[rgba(0,0,85,0.02)] h-[249px] relative rounded-tl-[16px] rounded-tr-[16px] shrink-0 w-full">
      <div aria-hidden="true" className="absolute border border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-tl-[16px] rounded-tr-[16px]" />
      <div className="flex flex-col items-center size-full">
        <div className="box-border content-stretch flex flex-col h-[249px] items-center justify-between p-[32px] relative w-full">
          <Frame1000001912 />
          <Frame1000001916 />
        </div>
      </div>
    </div>
  );
}

function Thumb() {
  return (
    <div className="absolute bg-white right-[-8.33px] rounded-[6px] size-[16px] top-1/2 translate-y-[-50%]" data-name="thumb">
      <div aria-hidden="true" className="absolute border border-[#cdced6] border-solid inset-[-1px] pointer-events-none rounded-[7px]" />
    </div>
  );
}

function Thumb1() {
  return (
    <div className="absolute bg-white left-[-8px] rounded-[6px] size-[16px] top-1/2 translate-y-[-50%]" data-name="thumb">
      <div aria-hidden="true" className="absolute border border-[#cdced6] border-solid inset-[-1px] pointer-events-none rounded-[7px]" />
    </div>
  );
}

function Range() {
  return (
    <div className="absolute bg-[#d6f1df] h-[12px] left-[12.55%] right-[62.45%] rounded-[3px] top-1/2 translate-y-[-50%]" data-name="range">
      <div aria-hidden="true" className="absolute border border-[rgba(0,9,50,0.12)] border-solid inset-0 pointer-events-none rounded-[3px]" />
      <Thumb />
      <Thumb1 />
    </div>
  );
}

function Track() {
  return (
    <div className="basis-0 bg-[rgba(0,0,51,0.06)] content-stretch flex grow h-[12px] items-start min-h-px min-w-px relative rounded-[3px] shrink-0" data-name="track">
      <div aria-hidden="true" className="absolute border border-[rgba(0,9,50,0.12)] border-solid inset-0 pointer-events-none rounded-[3px]" />
      <Range />
    </div>
  );
}

function Slider() {
  return (
    <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[12px] items-center relative shrink-0 w-full" data-name="Slider">
      <Track />
    </div>
  );
}

function Frame1000001821() {
  return (
    <div className="content-stretch flex flex-col gap-[10px] h-[67px] items-center justify-center relative shrink-0 w-full">
      <Slider />
    </div>
  );
}

function Frame1000001917() {
  return (
    <div className="content-stretch flex gap-[10px] items-center relative shrink-0 w-[200px]">
      <p className="font-['SF_Pro:Regular',sans-serif] font-normal leading-[16px] relative shrink-0 text-[#1c2024] text-[12px] text-right tracking-[0.04px] w-[39px]" style={{ fontVariationSettings: "'wdth' 100" }}>
        2030
      </p>
    </div>
  );
}

function Frame1000001820() {
  return (
    <div className="content-stretch flex items-center justify-between relative shrink-0 w-full">
      <p className="font-['SF_Pro:Regular',sans-serif] font-normal leading-[16px] relative shrink-0 text-[#1c2024] text-[12px] text-right tracking-[0.04px] w-[50px]" style={{ fontVariationSettings: "'wdth' 100" }}>
        2024
      </p>
      <Frame1000001917 />
    </div>
  );
}

function Frame1000001754() {
  return (
    <div className="bg-[rgba(0,0,85,0.02)] h-[111px] relative rounded-bl-[16px] rounded-br-[16px] shrink-0 w-full">
      <div aria-hidden="true" className="absolute border-[0px_1px_1px] border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-bl-[16px] rounded-br-[16px]" />
      <div className="flex flex-col items-center size-full">
        <div className="box-border content-stretch flex flex-col h-[111px] items-center justify-between px-[32px] py-[16px] relative w-full">
          <Frame1000001821 />
          <Frame1000001820 />
        </div>
      </div>
    </div>
  );
}

function Frame1000001913() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-start min-h-px min-w-px relative shrink-0">
      <Frame1000001752 />
      <Frame1000001754 />
    </div>
  );
}

function Frame1000001918() {
  return (
    <div className="content-stretch flex items-center justify-between relative shrink-0 w-full">
      <div className="flex flex-col font-['Inter:Bold',sans-serif] font-bold justify-center leading-[0] not-italic relative shrink-0 text-[#1c2024] text-[18px] text-nowrap tracking-[-0.04px]">
        <p className="leading-[26px] whitespace-pre">{`MID-TERM `}</p>
      </div>
      <div className="relative rounded-[8px] shrink-0 size-[40px]" data-name="TrendUp">
        <div className="absolute inset-0" data-name="Vector">
          <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
            <g id="Vector"></g>
          </svg>
        </div>
        <div className="absolute inset-[21.88%_9.38%_28.13%_9.38%]" data-name="Vector">
          <div className="absolute inset-[-5%_-3.08%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 35 22">
              <path d={svgPaths.p3e249800} id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
        <div className="absolute inset-[21.88%_9.38%_53.13%_65.63%]" data-name="Vector">
          <div className="absolute inset-[-10%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 12 12">
              <path d="M11 11V1H1" id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame1000001919() {
  return (
    <div className="content-stretch flex flex-col font-['Inter:Regular',sans-serif] font-normal gap-[12px] items-start leading-[0] not-italic relative shrink-0 text-[#1c2024] text-[16px] w-full">
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Plan for gradual productivity gains</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Anticipate regulatory changes</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Build energy-efficient operations</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Start workforce adaptation</p>
      </div>
    </div>
  );
}

function Frame1000001753() {
  return (
    <div className="bg-[rgba(0,0,85,0.02)] h-[249px] relative rounded-tl-[16px] rounded-tr-[16px] shrink-0 w-full">
      <div aria-hidden="true" className="absolute border border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-tl-[16px] rounded-tr-[16px]" />
      <div className="flex flex-col items-center size-full">
        <div className="box-border content-stretch flex flex-col h-[249px] items-center justify-between p-[32px] relative w-full">
          <Frame1000001918 />
          <Frame1000001919 />
        </div>
      </div>
    </div>
  );
}

function Thumb2() {
  return (
    <div className="absolute bg-white right-[-8.33px] rounded-[6px] size-[16px] top-1/2 translate-y-[-50%]" data-name="thumb">
      <div aria-hidden="true" className="absolute border border-[#cdced6] border-solid inset-[-1px] pointer-events-none rounded-[7px]" />
    </div>
  );
}

function Thumb3() {
  return (
    <div className="absolute bg-white left-[-8px] rounded-[6px] size-[16px] top-1/2 translate-y-[-50%]" data-name="thumb">
      <div aria-hidden="true" className="absolute border border-[#cdced6] border-solid inset-[-1px] pointer-events-none rounded-[7px]" />
    </div>
  );
}

function Range1() {
  return (
    <div className="absolute bg-[#ffdfb5] h-[12px] left-[37.67%] right-[37.33%] rounded-[3px] top-1/2 translate-y-[-50%]" data-name="range">
      <div aria-hidden="true" className="absolute border border-[rgba(0,9,50,0.12)] border-solid inset-0 pointer-events-none rounded-[3px]" />
      <Thumb2 />
      <Thumb3 />
    </div>
  );
}

function Track1() {
  return (
    <div className="basis-0 bg-[rgba(0,0,51,0.06)] content-stretch flex grow h-[12px] items-start min-h-px min-w-px relative rounded-[3px] shrink-0" data-name="track">
      <div aria-hidden="true" className="absolute border border-[rgba(0,9,50,0.12)] border-solid inset-0 pointer-events-none rounded-[3px]" />
      <Range1 />
    </div>
  );
}

function Slider1() {
  return (
    <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[12px] items-center relative shrink-0 w-full" data-name="Slider">
      <Track1 />
    </div>
  );
}

function Frame1000001822() {
  return (
    <div className="content-stretch flex flex-col gap-[10px] h-[67px] items-center justify-center relative shrink-0 w-full">
      <Slider1 />
    </div>
  );
}

function Frame1000001920() {
  return (
    <div className="content-stretch flex gap-[10px] items-center relative shrink-0 w-[130px]">
      <p className="font-['SF_Pro:Regular',sans-serif] font-normal leading-[16px] relative shrink-0 text-[#1c2024] text-[12px] text-right tracking-[0.04px] w-[39px]" style={{ fontVariationSettings: "'wdth' 100" }}>
        2033
      </p>
    </div>
  );
}

function Frame1000001823() {
  return (
    <div className="content-stretch flex items-center justify-between relative shrink-0 w-full">
      <p className="font-['SF_Pro:Regular',sans-serif] font-normal leading-[16px] relative shrink-0 text-[#1c2024] text-[12px] text-right tracking-[0.04px] w-[121px]" style={{ fontVariationSettings: "'wdth' 100" }}>
        2027
      </p>
      <Frame1000001920 />
    </div>
  );
}

function Frame1000001755() {
  return (
    <div className="bg-[rgba(0,0,85,0.02)] h-[111px] relative rounded-bl-[16px] rounded-br-[16px] shrink-0 w-full">
      <div aria-hidden="true" className="absolute border-[0px_1px_1px] border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-bl-[16px] rounded-br-[16px]" />
      <div className="flex flex-col items-center size-full">
        <div className="box-border content-stretch flex flex-col h-[111px] items-center justify-between px-[32px] py-[16px] relative w-full">
          <Frame1000001822 />
          <Frame1000001823 />
        </div>
      </div>
    </div>
  );
}

function Frame1000001914() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-start min-h-px min-w-px relative shrink-0">
      <Frame1000001753 />
      <Frame1000001755 />
    </div>
  );
}

function Frame1000001921() {
  return (
    <div className="content-stretch flex items-center justify-between relative shrink-0 w-full">
      <div className="flex flex-col font-['Inter:Bold',sans-serif] font-bold justify-center leading-[0] not-italic relative shrink-0 text-[#1c2024] text-[18px] text-nowrap tracking-[-0.04px]">
        <p className="leading-[26px] whitespace-pre">LONG-TERM (2032+)</p>
      </div>
      <div className="relative rounded-[8px] shrink-0 size-[40px]" data-name="ArrowsHorizontal">
        <div className="absolute inset-0" data-name="Vector">
          <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
            <g id="Vector"></g>
          </svg>
        </div>
        <div className="absolute inset-[37.5%_78.13%_37.5%_9.38%]" data-name="Vector">
          <div className="absolute inset-[-10%_-20%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 7 12">
              <path d="M6 1L1 6L6 11" id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
        <div className="absolute inset-[37.5%_9.38%_37.5%_78.13%]" data-name="Vector">
          <div className="absolute inset-[-10%_-20%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 7 12">
              <path d="M1 1L6 6L1 11" id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
        <div className="absolute bottom-1/2 left-[9.38%] right-[9.38%] top-1/2" data-name="Vector">
          <div className="absolute inset-[-1px_-3.08%]" style={{ "--stroke-0": "rgba(28, 32, 36, 1)" } as React.CSSProperties}>
            <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 35 2">
              <path d="M1 1H33.5" id="Vector" stroke="var(--stroke-0, #1C2024)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame1000001922() {
  return (
    <div className="content-stretch flex flex-col font-['Inter:Regular',sans-serif] font-normal gap-[12px] items-start leading-[0] not-italic relative shrink-0 text-[#1c2024] text-[16px] w-full">
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Expect delayed but significant ROI</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Prepare for sectoral transformation</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Invest in continuous re-skilling</p>
      </div>
      <div className="flex flex-col justify-center relative shrink-0 w-full">
        <p className="leading-[24px]">Monitor AGI developments</p>
      </div>
    </div>
  );
}

function Frame1000001756() {
  return (
    <div className="bg-[rgba(0,0,85,0.02)] h-[249px] relative rounded-tl-[16px] rounded-tr-[16px] shrink-0 w-full">
      <div aria-hidden="true" className="absolute border border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-tl-[16px] rounded-tr-[16px]" />
      <div className="flex flex-col items-center size-full">
        <div className="box-border content-stretch flex flex-col h-[249px] items-center justify-between p-[32px] relative w-full">
          <Frame1000001921 />
          <Frame1000001922 />
        </div>
      </div>
    </div>
  );
}

function Thumb4() {
  return (
    <div className="absolute bg-white left-[-8px] rounded-[6px] size-[16px] top-1/2 translate-y-[-50%]" data-name="thumb">
      <div aria-hidden="true" className="absolute border border-[#cdced6] border-solid inset-[-1px] pointer-events-none rounded-[7px]" />
    </div>
  );
}

function Range2() {
  return (
    <div className="absolute bg-[#ffdbdc] h-[12px] left-[61.6%] right-0 rounded-[3px] top-[calc(50%+0.5px)] translate-y-[-50%]" data-name="range">
      <div aria-hidden="true" className="absolute border border-[rgba(0,9,50,0.12)] border-solid inset-0 pointer-events-none rounded-[3px]" />
      <Thumb4 />
    </div>
  );
}

function Track2() {
  return (
    <div className="basis-0 bg-[rgba(0,0,51,0.06)] content-stretch flex grow h-[12px] items-start min-h-px min-w-px relative rounded-[3px] shrink-0" data-name="track">
      <div aria-hidden="true" className="absolute border border-[rgba(0,9,50,0.12)] border-solid inset-0 pointer-events-none rounded-[3px]" />
      <Range2 />
    </div>
  );
}

function Slider2() {
  return (
    <div className="bg-[rgba(255,255,255,0)] content-stretch flex h-[12px] items-center relative shrink-0 w-full" data-name="Slider">
      <Track2 />
    </div>
  );
}

function Frame1000001824() {
  return (
    <div className="content-stretch flex flex-col gap-[10px] h-[67px] items-center justify-center relative shrink-0 w-full">
      <Slider2 />
    </div>
  );
}

function Frame1000001923() {
  return (
    <div className="content-stretch flex gap-[10px] items-center justify-end relative shrink-0 w-[68px]">
      <p className="font-['SF_Pro:Regular',sans-serif] font-normal leading-[16px] relative shrink-0 text-[#1c2024] text-[12px] text-right tracking-[0.04px] w-[39px]" style={{ fontVariationSettings: "'wdth' 100" }}>
        2032+
      </p>
    </div>
  );
}

function Frame1000001825() {
  return (
    <div className="content-stretch flex gap-[317px] items-center justify-end relative shrink-0 w-[279px]">
      <Frame1000001923 />
    </div>
  );
}

function Frame1000001757() {
  return (
    <div className="bg-[rgba(0,0,85,0.02)] h-[111px] relative rounded-bl-[16px] rounded-br-[16px] shrink-0 w-full">
      <div aria-hidden="true" className="absolute border-[0px_1px_1px] border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-bl-[16px] rounded-br-[16px]" />
      <div className="flex flex-col items-center size-full">
        <div className="box-border content-stretch flex flex-col h-[111px] items-center justify-between px-[32px] py-[16px] relative w-full">
          <Frame1000001824 />
          <Frame1000001825 />
        </div>
      </div>
    </div>
  );
}

function Frame1000001915() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-start min-h-px min-w-px relative shrink-0">
      <Frame1000001756 />
      <Frame1000001757 />
    </div>
  );
}

function Timeline() {
  return (
    <div className="content-stretch flex gap-[8px] items-center relative shrink-0 w-full" data-name="Timeline">
      <Frame1000001913 />
      <Frame1000001914 />
      <Frame1000001915 />
    </div>
  );
}

function TextContainer() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-start justify-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-center relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Bold',sans-serif] font-bold grow leading-[26px] min-h-px min-w-px relative shrink-0 text-[#1c2024] text-[18px] tracking-[-0.04px]" style={{ fontVariationSettings: "'wdth' 100" }}>
          Executive Decision Framework
        </p>
      </div>
    </div>
  );
}

function TextContainer1() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Gradual Evolution</p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Inter:Regular',sans-serif] font-normal grow leading-[20px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[14px]">Plan for steady AI progress over decades, not exponential breakthroughs</p>
      </div>
    </div>
  );
}

function TextContainer2() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Workforce Development</p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Inter:Regular',sans-serif] font-normal grow leading-[20px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[14px]">Start re-skilling programs now for long-term adaptation</p>
      </div>
    </div>
  );
}

function TextContainer3() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Sustainable Investment</p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Inter:Regular',sans-serif] font-normal grow leading-[20px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[14px]">Avoid hype-driven spending; focus on proven AI applications</p>
      </div>
    </div>
  );
}

function TextContainer4() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Risk Management</p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Inter:Regular',sans-serif] font-normal grow leading-[20px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[14px]">Prepare for 2025-2030 market correction while maintaining strategic AI investments</p>
      </div>
    </div>
  );
}

function TextContainer5() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Infrastructure First</p>
      </div>
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Inter:Regular',sans-serif] font-normal grow leading-[20px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[14px]">Secure reliable data and energy infrastructure before scaling</p>
      </div>
    </div>
  );
}

function Frame1000001848() {
  return (
    <div className="gap-[16px] grid grid-cols-[repeat(2,_minmax(0px,_1fr))] grid-rows-[repeat(3,_minmax(0px,_1fr))] h-[409px] relative shrink-0 w-full">
      <div className="[grid-area:1_/_1] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start px-[32px] py-[16px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=2">
              <TextContainer1 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:1_/_2] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start px-[32px] py-[16px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=2">
              <TextContainer2 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:2_/_1] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start px-[32px] py-[16px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=2">
              <TextContainer3 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:2_/_2] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start px-[32px] py-[16px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=2">
              <TextContainer4 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:3_/_1] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start px-[32px] py-[16px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=2">
              <TextContainer5 />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Card1() {
  return (
    <div className="bg-[rgba(255,156,0,0.16)] relative rounded-[16px] shrink-0 w-full" data-name="Card">
      <div className="overflow-clip rounded-[inherit] size-full">
        <div className="box-border content-stretch flex flex-col gap-[24px] items-start p-[32px] relative w-full">
          <div className="box-border content-stretch flex flex-col items-start overflow-clip px-0 py-[12px] relative rounded-[12px] shrink-0 w-full" data-name="Card">
            <div className="content-stretch flex gap-[12px] items-center overflow-clip relative shrink-0 w-full" data-name="type=1">
              <div className="relative rounded-[8px] shrink-0 size-[40px]" data-name="ShieldCheck">
                <div className="absolute inset-0" data-name="Vector">
                  <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
                    <g id="Vector"></g>
                  </svg>
                </div>
                <div className="absolute inset-[18.75%_15.63%_9.38%_15.63%]" data-name="Vector">
                  <div className="absolute inset-[-3.48%_-3.64%]" style={{ "--stroke-0": "rgba(246, 94, 0, 1)" } as React.CSSProperties}>
                    <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 30 31">
                      <path d={svgPaths.pa767f00} id="Vector" stroke="var(--stroke-0, #F65E00)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.917647" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
                <div className="absolute inset-[40.63%_34.38%_37.5%_34.38%]" data-name="Vector">
                  <div className="absolute inset-[-11.43%_-8%]" style={{ "--stroke-0": "rgba(246, 94, 0, 1)" } as React.CSSProperties}>
                    <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 15 11">
                      <path d="M1 6L4.75 9.75L13.5 1" id="Vector" stroke="var(--stroke-0, #F65E00)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.917647" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
              </div>
              <TextContainer />
            </div>
          </div>
          <Frame1000001848 />
        </div>
      </div>
      <div aria-hidden="true" className="absolute border border-[rgba(255,129,0,0.49)] border-solid inset-0 pointer-events-none rounded-[16px]" />
    </div>
  );
}

function TextContainer6() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-start justify-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-center relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Bold',sans-serif] font-bold grow leading-[26px] min-h-px min-w-px relative shrink-0 text-[#1c2024] text-[18px] tracking-[-0.04px]" style={{ fontVariationSettings: "'wdth' 100" }}>
          Next Steps:
        </p>
      </div>
    </div>
  );
}

function ContentContainer6() {
  return (
    <div className="bg-[rgba(0,22,0,0.09)] content-stretch flex items-center justify-center overflow-clip relative rounded-[3px] shrink-0 size-[24px]" data-name="content-container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="size=1, weight=light, align=left ✦, highContrast=false">
        <p className="font-['Inter:Light',sans-serif] font-light leading-[16px] not-italic relative shrink-0 text-[12px] text-[rgba(0,7,20,0.62)] text-nowrap tracking-[0.04px] whitespace-pre">1</p>
      </div>
    </div>
  );
}

function TextContainer7() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Assess current AI investments against these timelines</p>
      </div>
    </div>
  );
}

function ContentContainer7() {
  return (
    <div className="bg-[rgba(0,22,0,0.09)] content-stretch flex items-center justify-center overflow-clip relative rounded-[3px] shrink-0 size-[24px]" data-name="content-container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="size=1, weight=light, align=left ✦, highContrast=false">
        <p className="font-['Inter:Light',sans-serif] font-light leading-[16px] not-italic relative shrink-0 text-[12px] text-[rgba(0,7,20,0.62)] text-nowrap tracking-[0.04px] whitespace-pre">2</p>
      </div>
    </div>
  );
}

function TextContainer8() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <div className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">
          <p className="mb-0">Develop infrastructure partnership strategy</p>
          <p>&nbsp;</p>
        </div>
      </div>
    </div>
  );
}

function ContentContainer8() {
  return (
    <div className="bg-[rgba(0,22,0,0.09)] content-stretch flex items-center justify-center overflow-clip relative rounded-[3px] shrink-0 size-[24px]" data-name="content-container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="size=1, weight=light, align=left ✦, highContrast=false">
        <p className="font-['Inter:Light',sans-serif] font-light leading-[16px] not-italic relative shrink-0 text-[12px] text-[rgba(0,7,20,0.62)] text-nowrap tracking-[0.04px] whitespace-pre">3</p>
      </div>
    </div>
  );
}

function TextContainer9() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Create workforce transition roadmap</p>
      </div>
    </div>
  );
}

function ContentContainer9() {
  return (
    <div className="bg-[rgba(0,22,0,0.09)] content-stretch flex items-center justify-center overflow-clip relative rounded-[3px] shrink-0 size-[24px]" data-name="content-container">
      <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-start relative shrink-0" data-name="size=1, weight=light, align=left ✦, highContrast=false">
        <p className="font-['Inter:Light',sans-serif] font-light leading-[16px] not-italic relative shrink-0 text-[12px] text-[rgba(0,7,20,0.62)] text-nowrap tracking-[0.04px] whitespace-pre">4</p>
      </div>
    </div>
  );
}

function TextContainer10() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-center min-h-px min-w-px relative shrink-0" data-name="text-container">
      <div className="bg-[rgba(255,255,255,0)] box-border content-stretch flex items-start pb-[12px] pt-0 px-0 relative shrink-0 w-full" data-name="Text">
        <p className="basis-0 font-['Open_Sans:Medium',sans-serif] grow leading-[24px] min-h-px min-w-px not-italic relative shrink-0 text-[#1c2024] text-[16px]">Establish market volatility contingency plans</p>
      </div>
    </div>
  );
}

function Frame1000001849() {
  return (
    <div className="gap-[16px] grid grid-cols-[repeat(2,_minmax(0px,_1fr))] grid-rows-[repeat(2,_minmax(0px,_1fr))] h-[267.333px] relative shrink-0 w-full">
      <div className="[grid-area:1_/_1] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start p-[12px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=1">
              <div className="content-stretch flex flex-col items-start relative shrink-0" data-name="Icon Button">
                <ContentContainer6 />
              </div>
              <TextContainer7 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:1_/_2] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start p-[12px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=1">
              <div className="content-stretch flex flex-col items-start relative shrink-0" data-name="Icon Button">
                <ContentContainer7 />
              </div>
              <TextContainer8 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:2_/_1] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start p-[12px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=1">
              <div className="content-stretch flex flex-col items-start relative shrink-0" data-name="Icon Button">
                <ContentContainer8 />
              </div>
              <TextContainer9 />
            </div>
          </div>
        </div>
      </div>
      <div className="[grid-area:2_/_2] bg-[rgba(255,255,255,0.9)] relative rounded-[12px] shrink-0" data-name="Card">
        <div className="overflow-clip rounded-[inherit] size-full">
          <div className="box-border content-stretch flex flex-col items-start p-[12px] relative size-full">
            <div className="box-border content-stretch flex gap-[12px] items-start overflow-clip px-0 py-[12px] relative shrink-0 w-full" data-name="type=1">
              <div className="content-stretch flex flex-col items-start relative shrink-0" data-name="Icon Button">
                <ContentContainer9 />
              </div>
              <TextContainer10 />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Card2() {
  return (
    <div className="bg-[rgba(0,32,0,0.06)] relative rounded-[16px] shrink-0 w-full" data-name="Card">
      <div className="overflow-clip rounded-[inherit] size-full">
        <div className="box-border content-stretch flex flex-col gap-[24px] items-start p-[32px] relative w-full">
          <div className="box-border content-stretch flex flex-col items-start overflow-clip px-0 py-[12px] relative rounded-[12px] shrink-0 w-full" data-name="Card">
            <div className="content-stretch flex gap-[12px] items-center overflow-clip relative shrink-0 w-full" data-name="type=1">
              <div className="relative rounded-[8px] shrink-0 size-[40px]" data-name="Stairs">
                <div className="absolute inset-0" data-name="Vector">
                  <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 32 32">
                    <g id="Vector"></g>
                  </svg>
                </div>
                <div className="absolute inset-[37.5%_18.75%_31.25%_18.75%]" data-name="Vector">
                  <div className="absolute inset-[-8%_-4%]" style={{ "--stroke-0": "rgba(5, 15, 0, 1)" } as React.CSSProperties}>
                    <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 27 15">
                      <path d="M1 13.5H9.75V7.25H17.25V1H26" id="Vector" stroke="var(--stroke-0, #050F00)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.470588" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
                <div className="absolute inset-[12.5%_18.75%]" data-name="Vector">
                  <div className="absolute inset-[-3.33%_-4%]" style={{ "--stroke-0": "rgba(5, 15, 0, 1)" } as React.CSSProperties}>
                    <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 27 32">
                      <path d={svgPaths.p37ad37f2} id="Vector" stroke="var(--stroke-0, #050F00)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.470588" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
                <div className="absolute inset-[68.75%_18.75%_31.25%_40.63%]" data-name="Vector">
                  <div className="absolute inset-[-1px_-6.15%]" style={{ "--stroke-0": "rgba(5, 15, 0, 1)" } as React.CSSProperties}>
                    <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 19 2">
                      <path d="M1 1H17.25" id="Vector" stroke="var(--stroke-0, #050F00)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.470588" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
                <div className="absolute inset-[53.13%_18.75%_46.88%_59.38%]" data-name="Vector">
                  <div className="absolute inset-[-1px_-11.43%]" style={{ "--stroke-0": "rgba(5, 15, 0, 1)" } as React.CSSProperties}>
                    <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 11 2">
                      <path d="M1 1H9.75" id="Vector" stroke="var(--stroke-0, #050F00)" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.470588" strokeWidth="2" />
                    </svg>
                  </div>
                </div>
              </div>
              <TextContainer6 />
            </div>
          </div>
          <Frame1000001849 />
        </div>
      </div>
      <div aria-hidden="true" className="absolute border border-[rgba(0,20,0,0.16)] border-solid inset-0 pointer-events-none rounded-[16px]" />
    </div>
  );
}

function Card3() {
  return (
    <div className="bg-white relative rounded-bl-[16px] rounded-br-[16px] shrink-0 w-full" data-name="Card">
      <div className="overflow-clip rounded-[inherit] size-full">
        <div className="box-border content-stretch flex flex-col gap-[64px] items-start px-[32px] py-[48px] relative w-full">
          <CardContainer1 />
          <div className="bg-[rgba(255,255,255,0)] content-stretch flex items-center overflow-clip relative shrink-0 w-full" data-name="Separator">
            <div className="basis-0 bg-[rgba(0,0,47,0.15)] grow h-px min-h-px min-w-px shrink-0" data-name="line" />
          </div>
          <CardContent4 />
          <Timeline />
          <Card1 />
          <Card2 />
        </div>
      </div>
      <div aria-hidden="true" className="absolute border-[0px_1px_1px] border-[rgba(0,0,47,0.15)] border-solid inset-0 pointer-events-none rounded-bl-[16px] rounded-br-[16px]" />
    </div>
  );
}

function ContentContainer10() {
  return (
    <div className="content-stretch flex flex-col items-start relative shrink-0 w-full" data-name="Content Container">
      <Card />
      <Card3 />
    </div>
  );
}

function MainContent() {
  return (
    <div className="relative shrink-0 w-full" data-name="Main Content">
      <div className="size-full">
        <div className="box-border content-stretch flex flex-col gap-[48px] items-start p-[32px] relative w-full">
          <ContentContainer10 />
        </div>
      </div>
    </div>
  );
}

export default function NavBar1({ data, loading, onConfigureClick }: { data?: any; loading?: boolean; onConfigureClick?: () => void }) {
  return (
    <div className="content-stretch flex flex-col items-center relative size-full" data-name="<NavBar>">
      <NavBar onConfigureClick={onConfigureClick} />
      <MainContent data={data} loading={loading} />
    </div>
  );
}