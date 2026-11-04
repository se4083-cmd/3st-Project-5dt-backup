import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../App";
import { TicketList } from "../components";

const mount = (route = "/") =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  );
const choose = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
describe("week 1 screens", () => {
  it("does not describe missing preview rows as zero pending tickets", () => {
    render(
      <MemoryRouter>
        <TicketList items={[]} total={4} asOf="2026-11-02T01:00:00Z" />
      </MemoryRouter>,
    );
    expect(
      screen.getByText("검토 대기 4건의 미리보기가 제공되지 않았습니다.", {
        exact: false,
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("지금 확인할 문의가 없습니다"),
    ).not.toBeInTheDocument();
  });
  it("renders the design and carries workload filters into the next route", async () => {
    mount();
    const card = await screen.findByRole("link", {
      name: "검토 대기 4건 목록",
    });
    expect(screen.getByText("78.3%")).toBeInTheDocument();
    expect(
      screen.getByText("6", { selector: ".followup-count strong" }),
    ).toBeInTheDocument();
    fireEvent.click(card);
    expect(await screen.findByRole("heading", { name: "문의 예외 큐" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "T-2401 →" })).toBeInTheDocument();
  });
  it("distinguishes empty, unready, stale and loading states", async () => {
    mount();
    await screen.findByText("78.3%");
    choose("응답 상태", "not_ready");
    expect(
      await screen.findByText("아직 분석 결과가 없습니다"),
    ).toBeInTheDocument();
    expect(screen.queryByText("78.3%")).not.toBeInTheDocument();
    choose("응답 상태", "stale");
    expect(await screen.findByText("이전 정상 결과")).toBeInTheDocument();
    expect(screen.getByText("78.3%")).toBeInTheDocument();
    choose("응답 상태", "empty");
    expect(
      await screen.findByText("지금 확인할 문의가 없습니다"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "검토 대기 0건 목록" }),
    ).toBeInTheDocument();
    choose("응답 상태", "loading");
    await waitFor(() =>
      expect(screen.queryByText("T-2401")).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("데이터 불러오는 중")).toBeInTheDocument();
  });
  it.each([
    ["401", "로그인이 필요합니다"],
    ["403", "이 화면을 볼 권한이 없습니다"],
    ["404", "대상을 찾을 수 없습니다"],
    ["409", "최신 상태를 확인해 주세요"],
    ["422", "조회 조건을 확인해 주세요"],
    ["429", "잠시 후 다시 시도해 주세요"],
    ["503", "서비스 연결이 지연되고 있습니다"],
    ["network", "연결을 확인해 주세요"],
  ])(
    "renders %s and clears prior protected content",
    async (value, heading) => {
      mount();
      await screen.findByText("T-2401");
      choose("응답 상태", value);
      expect(
        await screen.findByRole("heading", { name: heading }),
      ).toBeInTheDocument();
      expect(screen.queryByText("T-2401")).not.toBeInTheDocument();
      expect(screen.queryByText("78.3%")).not.toBeInTheDocument();
    },
  );
  it("restricts direct settings navigation and clears data on role change", async () => {
    mount();
    await screen.findByText("T-2401");
    choose("권한 프로필", "limited");
    expect(
      await screen.findByRole("link", { name: "검토 대기 1건 목록" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("T-2401")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "운영 설정" }),
    ).not.toBeInTheDocument();
    choose("권한 프로필", "customer");
    expect(
      await screen.findByText("이 화면을 볼 권한이 없습니다"),
    ).toBeInTheDocument();
    expect(screen.queryByText("T-2403")).not.toBeInTheDocument();
  });
  it("protects a direct URL independently of menu visibility", async () => {
    mount("/settings");
    await screen.findByRole("heading", { name: "자동화 운영", level: 1 });
    choose("권한 프로필", "limited");
    expect(
      await screen.findByText("이 화면을 볼 권한이 없습니다"),
    ).toBeInTheDocument();
    expect(screen.queryByText("현재 제어 상태")).not.toBeInTheDocument();
  });
  it("recovers the simulated expired session without retaining old data", async () => {
    mount();
    await screen.findByText("T-2401");
    choose("권한 프로필", "signed_out");
    const recover = await screen.findByRole("button", {
      name: "시연 로그인 복구",
    });
    expect(screen.queryByText("T-2401")).not.toBeInTheDocument();
    fireEvent.click(recover);
    expect(await screen.findByText("T-2401")).toBeInTheDocument();
  });
  it("keeps the exception queue inside the selected manager scope", async () => {
    mount("/inquiries");
    await screen.findByRole("link", { name: "T-2401 →" });
    choose("권한 프로필", "limited");
    expect(await screen.findByRole("link", { name: "T-2403 →" })).toBeInTheDocument();
    expect(screen.queryByText("T-2402 →")).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "미라우팅" })).not.toBeInTheDocument();
  });
  it("keeps VOC low-sample items distinct from scored products", async () => {
    mount("/products");
    await screen.findByRole("heading", { name: "VOC TOP 10" });
    expect(screen.getByText("점수 산정 불가")).toBeInTheDocument();
    expect(screen.getByText("0점 아님")).toBeInTheDocument();
    expect(screen.getByText("72.430000점")).toBeInTheDocument();
  });
  it("shows AI material limits and protects direct quality navigation", async () => {
    mount("/quality");
    const sample = await screen.findByRole("link", { name: /표본 44444444/ });
    fireEvent.click(sample);
    expect(await screen.findByRole("heading", { name: "품질 평가 자료" })).toBeInTheDocument();
    expect(await screen.findByText("평가 자료 부족")).toBeInTheDocument();
    choose("권한 프로필", "limited");
    expect(await screen.findByText("이 화면을 볼 권한이 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("상품이 파손되어 도착했어요.")).not.toBeInTheDocument();
  });
  it("opens scoped customer facts without calling them AI generated", async () => {
    mount("/inquiries/T-2401");
    const link = await screen.findByRole("link", { name: "허용된 고객 360 보기 →" });
    fireEvent.click(link);
    expect(await screen.findByRole("heading", { name: "고객 360" })).toBeInTheDocument();
    expect(await screen.findByText("AI 요약 아님")).toBeInTheDocument();
    expect(screen.getByText("허용된 문의 이력 3건")).toBeInTheDocument();
    choose("권한 프로필", "customer");
    expect(await screen.findByText("이 화면을 볼 권한이 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("허용된 문의 이력 3건")).not.toBeInTheDocument();
  });
});
