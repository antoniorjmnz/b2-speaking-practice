import { expect, test } from "@playwright/test";

const examinerAudioPaths = Array.from({ length: 4 }, (_, index) => {
  const number = String(index + 9).padStart(3, "0");
  return [
    `/assets/temporary-part2/examiner-p2-${number}-sonia.mp3`,
    `/assets/temporary-part2/examiner-p2-${number}-followup-sonia.mp3`,
  ];
}).flat();
examinerAudioPaths.push("/assets/temporary-part2/examiner-start-now-sonia.mp3");

test("las cuatro instrucciones originales y cierres de Sonia cargan en el navegador", async ({
  page,
}) => {
  await page.goto("/");
  const assets = await page.evaluate(async (paths) => {
    return Promise.all(
      paths.map(
        (path) =>
          new Promise<{ path: string; duration: number }>((resolve, reject) => {
            const audio = new Audio(path);
            const timeout = window.setTimeout(
              () => reject(new Error(`Timeout loading ${path}`)),
              5_000,
            );
            audio.preload = "metadata";
            audio.addEventListener(
              "loadedmetadata",
              () => {
                window.clearTimeout(timeout);
                resolve({ path, duration: audio.duration });
              },
              { once: true },
            );
            audio.addEventListener(
              "error",
              () => {
                window.clearTimeout(timeout);
                reject(new Error(`Cannot decode ${path}`));
              },
              { once: true },
            );
            audio.load();
          }),
      ),
    );
  }, examinerAudioPaths);

  expect(assets).toHaveLength(9);
  for (const asset of assets) {
    expect(asset.duration, asset.path).toBeGreaterThan(
      asset.path.includes("start-now") ? 0.8 : 4,
    );
    expect(asset.duration, asset.path).toBeLessThan(30);
  }
});
