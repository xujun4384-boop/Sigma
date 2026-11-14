import React from 'react';
import {Character as Her, CharacterSide as HerSide, CharacterBack as HerBack} from './generated/char-her';
import {Character as Hero, CharacterSide as HeroSide, CharacterBack as HeroBack} from './generated/char-hero';

export const CHAR_REGISTRY: Record<string, React.FC> = {'her': Her, 'her-side': HerSide, 'her-back': HerBack, 'hero': Hero, 'hero-side': HeroSide, 'hero-back': HeroBack};
