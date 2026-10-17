import { useState } from "react";
import { get, setPass, Unauthorized } from "../lib/api";

export function PassGate({ onUnlock }: { onUnlock: () => void }) {
  const [value, setValue] = useState("");
  const [wrong, setWrong] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPass(value);
    try {
      await get("/api/policy");
      onUnlock();
    } catch (err) {
      setWrong(err instanceof Unauthorized);
    }
  }

  return (
    <main className="gate">
      <h1>Bylaw</h1>
      <p>This demo runs a live agent on AWS, so it's behind a passcode. The passcode is in the hackathon submission.</p>
      <form onSubmit={submit}>
        <label className="visually-hidden" htmlFor="pass">Passcode</label>
        <input id="pass" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Passcode" />
        <button className="btn" type="submit">Open the desk</button>
      </form>
      {wrong && <p className="err" role="alert">That passcode didn't work. Check it and try again.</p>}
    </main>
  );
}
