import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
Config.setCodec('h264');
Config.setCrf(26);
Config.setPixelFormat('yuv420p');
Config.setConcurrency(4);
