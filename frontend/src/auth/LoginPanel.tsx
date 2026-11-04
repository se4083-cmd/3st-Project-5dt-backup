import { useState, type FormEvent } from "react";
import { AsyncState, PageHeading } from "../components";
import { useAuth, useAuthManager } from "./AuthProvider";

export function LoginPanel() {
  const auth = useAuthManager(), state = useAuth();
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const secret = password; setPassword("");
    await auth.login(loginName, secret);
  }
  return <>
    <PageHeading title="백엔드 로그인" subtitle="개발용 프로필과 별도의 실제 Backend A 인증입니다." />
    {state.error && <AsyncState kind="error" error={state.error} />}
    <form className="card p1-login" onSubmit={submit} aria-label="백엔드 로그인">
      <label>로그인 이름<input autoComplete="username" name="login_name" required minLength={3} maxLength={254} value={loginName} onChange={e => setLoginName(e.target.value)} /></label>
      <label>비밀번호<input autoComplete="current-password" name="password" type="password" required maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button className="button" type="submit">로그인</button>
      <p className="small muted">JWT는 메모리에만 보관합니다. 새로고침 후에는 다시 로그인합니다.</p>
    </form>
  </>;
}
