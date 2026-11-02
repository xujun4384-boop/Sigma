import React from 'react';
import {Character as Character, CharacterSide as CharacterSide, CharacterBack as CharacterBack} from './generated/char-hero';

export const CHAR_REGISTRY: Record<string, React.FC> = {'hero': Character, 'hero-side': CharacterSide, 'hero-back': CharacterBack};
