"""Camera/encoder diagnostic. No images or customer data are saved."""
import argparse
import logging
import time
from dataclasses import replace

from app.camera import CameraWorker
from app.config import load_settings


def main():
    parser = argparse.ArgumentParser(description="カメラと顔特徴量生成の診断（保存なし）")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    settings = load_settings()
    if args.index is not None:
        settings = replace(settings, camera_index=args.index)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    confirmed = []
    worker = CameraWorker(settings, lambda encoding: confirmed.append(len(encoding)))
    worker.start()
    try:
        time.sleep(max(1, min(args.seconds, 60)))
        print({"camera": worker.status(), "confirmed_faces": len(confirmed),
               "encoding_dimensions": sorted(set(confirmed))})
    finally:
        worker.stop()


if __name__ == "__main__":
    main()
